"""fpstune had no notion of a machine that runs off a battery.

That is a gap in the product rather than in one machine, and it matters because
two NVIDIA features exist purely to cap frame rate on a portable: Battery Boost
holds a game near 30 fps on battery, Whisper Mode holds it between 40 and 60 for
quiet running. Both are consequence-3 cases — a ceiling the player did not ask
for — and until this, nothing shipped could see either.

Two things are guarded here, and the second is the one that already produced a
wrong answer once. The machine class has to be derived rather than assumed. And
the NVIDIA App's criteria file has to be read as what it is: it reports whether
the cap is *possible*, never whether it is switched on, and collapsing those two
tells a user with the cap in force that they do not have it.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest

from fpstune.settings.applicability import ABSENT_READINGS, NOT_AVAILABLE
from fpstune.settings.base import SettingExecutor
from fpstune.settings.executors import nvidia_app

# The file this machine actually holds, read on 2026-08-23 and reproduced in
# shape. Messages are localised by the App — the real one is in Turkish on an
# English-language product — so nothing here may key off them.
REAL_SHAPE = {
    "criteria": {
        "overallState": False,
        "featureTile": "BatteryBoost2.0",
        "header": "Battery Boost 2.0",
        "message": "Automatically extend your battery life while gaming",
        "states": [
            {
                "name": "gpu",
                "message": "GeForce RTX laptop GPU, 3050 series or above",
                "state": True,
            },
            {"name": "os", "message": "Windows 10 or above", "state": True},
            {"name": "drvrVrsn", "message": "GeForce 510.59 driver or above", "state": True},
            {
                "name": "bb2",
                "message": "Supported per enabled nvAPI and JPAC platform",
                "state": False,
            },
        ],
    }
}


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    nvidia_app.reset_cache()
    yield
    nvidia_app.reset_cache()


def _write(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    target = tmp_path / "NVIDIA Corporation/NVIDIA App/NvBackend/batteryboost2.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig on purpose: the App writes a BOM, and a reader that assumed
    # plain utf-8 would report "no NVIDIA App" on a machine that has one.
    target.write_text(json.dumps(payload), encoding="utf-8-sig")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


class TestTheMachineClassIsDerived:
    def test_a_battery_probe_answers_without_starting_a_process(self) -> None:
        """The context is built per request (C7), so this cannot cost a process.

        PCSystemType would be the more precise answer and needs WMI. This reads
        GetSystemPowerStatus directly, so the only thing asserted here is that it
        returns an answer at all rather than raising or hanging.
        """
        from fpstune.settings.hardware_context import has_battery

        assert isinstance(has_battery(), bool)

    def test_the_answer_reaches_the_context_as_a_feature(self) -> None:
        # Settings gate on `feature: mobile`, so a probe that worked but never
        # reached `features` would hide every mobile setting silently.
        from fpstune.settings.hardware_context import build_hardware_context, has_battery

        context = build_hardware_context()
        assert ("mobile" in context.features) is has_battery()

    def test_a_desktop_is_not_called_portable(self) -> None:
        """BatteryFlag 128 means no system battery, 255 means the API does not know.

        Asserted against the interpretation rather than against a faked Win32
        call, so it holds on a machine of either kind — the point is which flag
        values mean "desktop", and that is decidable without one of each.

        255 matters as much as 128: an earlier draft treated only 128 as a
        desktop, which would have shown a laptop-only frame-cap warning on every
        machine whose firmware declined to answer.
        """
        from fpstune.settings.hardware_context import is_portable_flag

        assert is_portable_flag(128) is False, "no system battery"
        assert is_portable_flag(255) is False, "battery status unknown"

    def test_a_laptop_is(self) -> None:
        # Proves the check above is not simply always False. 1 is "high charge",
        # 8 is "charging" — both real readings from a machine with a battery.
        from fpstune.settings.hardware_context import is_portable_flag

        assert is_portable_flag(1) is True
        assert is_portable_flag(8) is True


class TestTheAppsCriteriaFileIsReadAsWhatItIs:
    def test_a_failing_criterion_means_no_cap_is_possible(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The real file on this machine: gpu, os and driver all pass, the
        # platform criterion `bb2` does not, and overallState is therefore false.
        _write(tmp_path, monkeypatch, REAL_SHAPE)

        assert nvidia_app.battery_boost_exposure() == nvidia_app.NO_CAP_POSSIBLE

    def test_bb2_is_an_entry_in_states_and_not_a_key(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The mistake this file exists to prevent, and it shipped for an hour.

        `bb2` is `{"name": "bb2", "state": false}` inside `states`, not a
        top-level key. A reader that looked it up as a key found nothing, fell
        through to `overallState`, and reported "the user switched it off" for a
        machine that cannot run the feature at all — the exact collapse of
        "unsupported" into "disabled" that the sentinel contract forbids.
        """
        _write(tmp_path, monkeypatch, REAL_SHAPE)

        assert "bb2" not in REAL_SHAPE["criteria"]
        assert nvidia_app.unmet_criteria() == ["bb2"]

    def test_all_criteria_passing_means_the_cap_is_one_toggle_away(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        supported = json.loads(json.dumps(REAL_SHAPE))
        supported["criteria"]["overallState"] = True
        for entry in supported["criteria"]["states"]:
            entry["state"] = True
        _write(tmp_path, monkeypatch, supported)

        assert nvidia_app.battery_boost_exposure() == nvidia_app.CAP_POSSIBLE
        assert nvidia_app.unmet_criteria() == []

    def test_no_file_is_an_absence_rather_than_an_all_clear(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "We could not read it" and "there is no cap" are different answers, and
        # reporting the first as the second is how a warning goes missing.
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        assert nvidia_app.battery_boost_exposure() == NOT_AVAILABLE
        assert NOT_AVAILABLE in ABSENT_READINGS

    def test_an_unreadable_file_is_an_absence_too(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "NVIDIA Corporation/NVIDIA App/NvBackend/batteryboost2.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{not json at all", encoding="utf-8")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        assert nvidia_app.battery_boost_exposure() == NOT_AVAILABLE

    def test_a_file_written_with_a_bom_still_reads(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The BOM already ate a config block once in this project, in CS2's
        # autoexec.cfg. Same trap, different file.
        _write(tmp_path, monkeypatch, REAL_SHAPE)
        raw = (tmp_path / "NVIDIA Corporation/NVIDIA App/NvBackend/batteryboost2.json").read_bytes()

        assert raw.startswith(b"\xef\xbb\xbf"), "the fixture is not exercising the BOM"
        assert nvidia_app.battery_boost_exposure() == nvidia_app.NO_CAP_POSSIBLE

    def test_a_missing_overall_state_is_not_guessed(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The App has reshaped this file across releases. A shape without the
        # field is unknown, not clear.
        _write(tmp_path, monkeypatch, {"criteria": {"states": []}})

        assert nvidia_app.battery_boost_exposure() == NOT_AVAILABLE


class TestTheAdvisorySettingSaysWhatItCanDo:
    @staticmethod
    def _setting() -> SettingExecutor:
        from fpstune.settings.definitions.gpu import NVIDIA_BATTERY_BOOST

        return NVIDIA_BATTERY_BOOST

    def test_it_never_claims_to_write_what_it_cannot(self) -> None:
        # The toggle lives in the NVIDIA App's UI. Nothing under NvBackend
        # persists it — the directory was searched — so an applyable setting here
        # would be a button that reports success and changes nothing.
        assert self._setting().is_readonly is True

    def test_it_is_offered_only_where_both_halves_are_true(self) -> None:
        # A desktop has no battery state to boost and an AMD laptop has no
        # NVIDIA App to read, so either condition alone is the wrong audience.
        conditions = self._setting().applicable_conditions
        assert conditions["gpu_vendor"] == "nvidia"
        assert conditions["feature"] == "mobile"

    def test_no_sentinel_is_listed_as_a_choice(self) -> None:
        # The sentinel contract: detection may emit `not_available`, and the
        # layer above turns it into "not on this machine". Listing it as a
        # choice would make it a value the user could be shown.
        assert not set(self._setting().choices) & ABSENT_READINGS

    def test_detection_can_only_answer_within_its_choices(self) -> None:
        assert nvidia_app.CAP_POSSIBLE in self._setting().choices
        assert nvidia_app.NO_CAP_POSSIBLE in self._setting().choices

    def test_the_ceiling_is_stated_rather_than_a_gain_invented(self) -> None:
        # 30 fps is a ceiling, and a ceiling cannot move the right way. The
        # verification engine will report this unmeasurable for that reason,
        # which is the honest outcome — not a percentage nobody measured.
        assert self._setting().impact_scores["fps_battery_ceiling"] == 30
