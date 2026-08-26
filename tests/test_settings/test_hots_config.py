"""Heroes of the Storm settings, and the file they are derived from.

Every key here was read off a real ``Variables.txt`` rather than a guide. That
is the whole reason HotS could be added at all while Valorant, Fortnite and Apex
could not: the file is plain ``key=value``, and a key the game does not read is
indistinguishable from one it does until the game rewrites the file on exit.

The defect the refresh-rate setting exists for was measured, not imagined: a
300 Hz panel with ``refreshrate=270`` written in the file, so the game drove the
display 30 Hz below its own capability and no graphics tweak could win that back.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from fpstune.settings.base import SettingScope, SettingValueType
from fpstune.settings.definitions.game_configs import (
    HOTS_SETTINGS,
    HOTS_VSYNC,
    create_hots_refresh_rate_setting,
    create_hots_sound_sample_rate_setting,
)
from fpstune.settings.executors import game_config_cache as gcc

SAMPLE = """\
alternateclock=false
GraphicsOptionShadowQuality=0
GraphicsOptionTextureQuality[2]=0
GraphicsOptionSSAO=2
localShadows=false
refreshrate=270
shadows=false
vsync=true
width=2560
"""


@pytest.fixture
def variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gcc, "_snapshot", lambda: {"hots": SAMPLE})


@pytest.mark.usefixtures("variables")
class TestReadingVariablesTxt:
    def test_reads_a_plain_key(self) -> None:
        assert gcc.get_hots_variable("vsync") == "true"

    def test_reads_a_key_the_game_wrote_with_its_own_index(self) -> None:
        # GraphicsOptionTextureQuality[2] — the bracketed slot is the game's.
        assert gcc.get_hots_variable("GraphicsOptionTextureQuality") == "0"

    def test_an_anchored_key_does_not_match_a_longer_one(self) -> None:
        # 'shadows' must not be answered by 'localShadows', and must not be
        # answered by GraphicsOptionShadowQuality either.
        assert gcc.get_hots_variable("shadows") == "false"
        assert gcc.get_hots_variable("GraphicsOptionShadowQuality") == "0"

    def test_matching_ignores_case_the_file_mixes_freely(self) -> None:
        assert gcc.get_hots_variable("VSync") == "true"
        assert gcc.get_hots_variable("graphicsoptionssao") == "2"

    def test_a_key_that_is_not_there_reads_as_absent(self) -> None:
        assert gcc.get_hots_variable("GraphicsOptionNoSuchThing") == gcc.NOT_INSTALLED

    def test_no_hots_at_all_reads_as_absent_not_as_a_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "false" here would claim a behaviour is off on a machine with no HotS.
        monkeypatch.setattr(gcc, "_snapshot", lambda: {"hots": None})
        assert gcc.get_hots_variable("vsync") == gcc.NOT_INSTALLED


class TestRefreshRateFollowsThePanel:
    def test_recommends_the_panels_own_rate(self) -> None:
        assert create_hots_refresh_rate_setting(300).recommended_value == "300"

    @pytest.mark.parametrize("hz", [60, 120, 144, 165, 240, 300, 360])
    def test_tracks_whatever_panel_is_attached(self, hz: int) -> None:
        assert create_hots_refresh_rate_setting(hz).recommended_value == str(hz)

    def test_the_measured_defect_is_named_by_the_setting(self) -> None:
        # 270 on a 300 Hz panel: the reading has to remain legal, because
        # reporting it is the setting's entire job.
        setting = create_hots_refresh_rate_setting(300)
        assert setting.choices == ()
        assert setting.value_type is SettingValueType.STRING

    def test_is_essential_scope(self) -> None:
        # A frame ceiling below the panel outweighs every graphics option here.
        assert create_hots_refresh_rate_setting(300).scope is SettingScope.ESSENTIAL

    def test_the_panel_rate_reaches_the_description(self) -> None:
        assert "300 Hz" in create_hots_refresh_rate_setting(300).description


class TestVsyncIsOffBecauseTheDriverAlreadySyncs:
    def test_recommends_off(self) -> None:
        assert HOTS_VSYNC.recommended_value == "false"

    def test_pairs_with_the_driver_setting_rather_than_repeating_it(self) -> None:
        # The documented configuration is driver V-Sync on, in-game V-Sync off.
        # Both on is the combination that costs latency without removing tearing
        # the driver had not already removed.
        from fpstune.settings.definitions.gpu import create_nvidia_vsync_setting

        assert create_nvidia_vsync_setting(vrr_available=True).recommended_value == "on"
        assert HOTS_VSYNC.recommended_value == "false"


class TestTheMixRateFollowsTheOutputDevice:
    """A game mixing below its endpoint throws away direction before Windows sees it."""

    @pytest.mark.parametrize(
        ("device_hz", "expected"),
        [(48000, "48000"), (96000, "48000"), (192000, "48000"), (44100, "44100"), (22050, "22050")],
    )
    def test_matches_the_device_without_inventing_a_level(
        self, device_hz: int, expected: str
    ) -> None:
        # 96 kHz endpoints are fed from 48 kHz without losing anything a game
        # emits, so the ladder stops at a rate the engine actually offers rather
        # than echoing the device number back.
        setting = create_hots_sound_sample_rate_setting(device_hz)
        assert setting.recommended_value == expected

    def test_the_measured_defect_is_the_one_it_names(self) -> None:
        # Variables.txt held 22050 while every active endpoint ran at 48000.
        setting = create_hots_sound_sample_rate_setting(48000)
        assert "22050" in setting.current_impact
        assert setting.recommended_value == "48000"

    def test_every_rung_of_the_ladder_is_a_legal_reading(self) -> None:
        # Detection reports whatever the file holds, so each value the ladder can
        # produce has to survive being read back (C6).
        for device_hz in (22050, 44100, 48000, 96000):
            setting = create_hots_sound_sample_rate_setting(device_hz)
            assert setting.recommended_value in setting.choices

    def test_it_is_not_sold_as_frames(self) -> None:
        setting = create_hots_sound_sample_rate_setting(48000)
        assert setting.impact_scores["fps"] == "0%"
        assert "footstep_clarity" in setting.impact_scores

    def test_the_device_rate_reaches_the_description(self) -> None:
        assert "96000 Hz" in create_hots_sound_sample_rate_setting(96000).description


class TestReadingTheOutputDeviceFormat:
    def test_the_blob_offset_is_the_measured_one(self) -> None:
        """The stored format carries an 8-byte header before WAVEFORMATEX.

        Reading from offset 0 produced "1 Hz, 0 channels" on a real 48 kHz
        endpoint, and an earlier attempt at offset 8 of the wrong field produced
        589822 Hz. This pins the offset that was verified against a device whose
        rate was known.
        """
        import struct

        from fpstune.utils import audio_format

        # Header, then WAVEFORMATEX for 48 kHz stereo 24-bit.
        blob = b"\x41\x00\x00\x00\x01\x00\x00\x00" + struct.pack(
            "<HHIIHH", 0xFFFE, 2, 48000, 288000, 6, 24
        )
        _tag, _ch, hz = struct.unpack_from("<HHI", blob, audio_format._FORMAT_OFFSET)
        assert hz == 48000

    def test_an_implausible_rate_is_rejected_rather_than_reported(self) -> None:
        # 1 and 589822 are what a wrong offset yields, and both reached a
        # recommendation before this bound existed.
        from fpstune.utils import audio_format

        low, high = audio_format._PLAUSIBLE
        assert not (low <= 1 <= high)
        assert not (low <= 589822 <= high)
        assert low <= 48000 <= high

    def test_it_answers_none_rather_than_guessing_off_windows(self) -> None:
        # A rate that could not be read must not become 44100: a recommendation
        # built from a guessed rate is the hardcoded-constant defect relocated.
        from fpstune.utils.audio_format import get_output_sample_rate_hz

        result = get_output_sample_rate_hz()
        assert result is None or 8000 <= result <= 384000


class TestApplyWritesWhatDetectionReads:
    def test_every_setting_writes_the_key_it_reads(self) -> None:
        # If these drift the setting can never verify: apply writes one key and
        # detection reports on another.
        for setting in HOTS_SETTINGS:
            assert setting.detect_args["batch_key"] == setting.apply_args["key"], setting.id

    def test_every_setting_routes_through_the_one_action(self) -> None:
        from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

        for setting in HOTS_SETTINGS:
            assert setting.apply_command == "hots_variable_set", setting.id
        assert "hots_variable_set" in ACTION_COMMANDS

    def test_the_action_preserves_the_games_own_index(self) -> None:
        # Dropping [n] on write leaves the key the game reads untouched and adds
        # a dead sibling — the defect MW3 paid for with its two profile shapes.
        from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

        script = ACTION_COMMANDS["hots_variable_set"]
        assert r"(\[\d+\])?" in script or r"(?:\[\d+\])?" in script

    def test_the_action_never_locks_the_file(self) -> None:
        # Locking MW3's options file froze every graphics setting the player
        # could change. HotS rewrites Variables.txt on exit the same way.
        from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

        script = ACTION_COMMANDS["hots_variable_set"]
        assert "-bnot [System.IO.FileAttributes]::ReadOnly" in script
        assert "Value ($attrs -bor" not in script

    def test_writes_are_serialised_against_each_other(self) -> None:
        # Each setting rewrites the whole file, so two concurrent applies would
        # drop one of the two writes.
        from fpstune.settings.executors.powershell_actions import _MUTEX_GROUPS

        assert any("hots_variable_set" in members for members in _MUTEX_GROUPS.values())


class TestQualityGates:
    def test_c2_every_setting_carries_a_non_stability_metric(self) -> None:
        for setting in [*HOTS_SETTINGS, create_hots_refresh_rate_setting(300)]:
            assert any(k != "stability" for k in setting.impact_scores), setting.id

    def test_c3_description_is_a_sentence_and_effect_is_a_phrase(self) -> None:
        for setting in [*HOTS_SETTINGS, create_hots_refresh_rate_setting(300)]:
            assert setting.description.rstrip().endswith("."), setting.id
            assert not setting.effect.rstrip().endswith("."), setting.id

    def test_c4_no_turkish_characters_in_user_facing_strings(self) -> None:
        forbidden = set("çğıİöşüÇĞÖŞÜ")
        for setting in [*HOTS_SETTINGS, create_hots_refresh_rate_setting(300)]:
            for text in (
                setting.display_name,
                setting.description,
                setting.effect,
                setting.recommended_impact,
            ):
                assert not (forbidden & set(str(text))), setting.id

    def test_c8_each_setting_owns_exactly_one_key(self) -> None:
        keys = [s.apply_args["key"] for s in HOTS_SETTINGS]
        assert len(keys) == len(set(keys)), f"two settings write the same key: {keys}"

    def test_a_heat_only_setting_is_not_sold_as_frames(self) -> None:
        # Cinematics buy nothing during a fight; claiming fps for them is the
        # conflation the project's fourth consequence exists to prevent.
        from fpstune.settings.definitions.game_configs import HOTS_MOVIES

        assert "fps" not in HOTS_MOVIES.impact_scores
        assert "gpu_temp_c" in HOTS_MOVIES.impact_scores


class TestAgainstTheInstalledGame:
    """Detection must never report a value the setting calls illegal (C6).

    Skipped when HotS is absent, because asserting against a file that is not
    there asserts nothing.
    """

    @pytest.fixture(scope="class")
    def real_file(self) -> str:
        candidates = [
            pathlib.Path(p)
            for p in (
                os.environ.get("FPSTUNE_HOTS_VARIABLES"),
                os.path.expandvars(r"%USERPROFILE%\Documents\Heroes of the Storm\Variables.txt"),
            )
            if p
        ]
        path = next((c for c in candidates if c.is_file()), None)
        if path is None:
            pytest.skip("Heroes of the Storm is not installed on this machine")
        return path.read_text(encoding="utf-8", errors="replace")

    def test_every_key_we_manage_exists_in_the_real_file(
        self, real_file: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gcc, "_snapshot", lambda: {"hots": real_file})
        missing = [
            s.id
            for s in HOTS_SETTINGS
            if gcc.get_hots_variable(s.apply_args["key"]) is gcc.NOT_INSTALLED
        ]
        assert not missing, f"settings whose key the game never wrote: {missing}"

    def test_no_reading_falls_outside_the_settings_own_choices(
        self, real_file: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gcc, "_snapshot", lambda: {"hots": real_file})
        illegal = {
            s.id: gcc.get_hots_variable(s.apply_args["key"])
            for s in HOTS_SETTINGS
            if s.choices and gcc.get_hots_variable(s.apply_args["key"]) not in s.choices
        }
        assert not illegal, f"detection would report values the setting rejects: {illegal}"
