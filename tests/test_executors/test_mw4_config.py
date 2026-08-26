"""Tests for MW4 (cod26) config discovery, reading and writing.

MW4 differs from every other game config fpstune touches in three ways, and each
one is a way to get it wrong on a machine other than the developer's:

* **Nothing in the path is stable.** The players directory carries a build tag,
  the directory below it is the user's Activision account id, and both filenames
  carry the build tag again. A test that only exercises the shapes present on
  one machine proves nothing, so the fixtures here deliberately use a *different*
  account id and a *different* build tag than any real install.
* **The same key name appears twice with different ranges.** ``DxrMode@0`` is
  Off/On and ``DxrMode@1`` is Off..Ultra. Writing one's value into the other
  hands the game something it will not accept.
* **The file states its own ranges.** No range in this suite is asserted from a
  constant fpstune holds; every one is read out of the sample's own comments.
"""

from __future__ import annotations

import codecs
import os
import threading
import time
from pathlib import Path

import pytest

from fpstune.settings.executors import game_config_cache as gcc
from fpstune.settings.executors import mw4_config
from fpstune.settings.executors.game_config_cache import (
    NOT_INSTALLED,
    get_mw4_metadata,
    get_mw4_option,
    mw4_config_paths,
)
from fpstune.settings.executors.mw4_config import Mw4ValueRejected, set_mw4_option
from fpstune.settings.executors.ps_batch import init_scan_cache, reset_scan_cache

# Trimmed from a real cod26 config, values changed. Note the LF line endings:
# the real file uses them even on Windows, and a writer that normalises to CRLF
# rewrites all of it while claiming to have changed one setting.
GLOBAL_SAMPLE = (
    "1\n"
    "\n"
    "//\n"
    "// Display\n"
    "\n"
    "// Percentage of window resolution that the 3D scene renders at.\n"
    "ResolutionMultiplier@0;64786;30730 = 50 // 0 to 200\n"
    "\n"
    "// Force specific aspect ratio independent of window aspect ratio\n"
    "AspectRatio@0;19775;7764 = auto // one of auto, standard, 5:4, wide 16:9\n"
    "\n"
    "// Voice device requested by the user\n"
    "VoiceOutputDevice@0;2059;35888 = \n"
    "\n"
    "// Refresh rate of used monitor\n"
    "RefreshRate@0;56178;35888 = Auto:165.000\n"
    "\n"
    "//\n"
    "// Graphics\n"
    "\n"
    "// Texture quality level, high to low ( higher number means lower resolution )\n"
    "TextureQuality@0;61129;7764 = 1 // 0 to 3\n"
    "\n"
    "// Enables DirectX Raytracing\n"
    "DxrMode@0;37334;7764 = Off // one of Off, On\n"
    "\n"
    "// Enables DirectX Raytracing\n"
    "DxrMode@1;8707;7764 = Off // one of Off, Low, Medium, High, Ultra\n"
    "\n"
    "// Allows locally stored files to be synced in with the cloud\n"
    "ConfigCloudStorageEnabled@0;57752;20945 = true\n"
    "\n"
    "// Set a target fraction of your PC's video memory to be used by the game\n"
    "VideoMemoryScaleMP@0;59710;7707 = 0.750000 // 0.000000 to 2.000000\n"
)

PROFILE_SAMPLE = (
    "1\n"
    "\n"
    "//\n"
    "// KBM Advanced\n"
    "\n"
    "// Adjusts the time required for moving before sprinting is auto activated.\n"
    "Sprint Assist Delay KBM@1;23176;7764 = 0 // 0 to 12750\n"
    "\n"
    "// Adjusts mouse acceleration\n"
    "MouseAcceleration@1;24278;7764 = 0.000000 // 0.000000 to 10.000000\n"
    "\n"
    "// On for muted tinnitus sound\n"
    "AltShellShock@0;57752;48403 = false\n"
)

# Neither of these matches any real install: the build tag is `rel` rather than
# the beta's, and the account id is not one that exists.
BUILD_TAG = "rel"
ACCOUNT_ID = "99887766"


@pytest.fixture
def scan_cache():
    _, token = init_scan_cache()
    yield
    reset_scan_cache(token)


@pytest.fixture
def mw4_install(tmp_path, monkeypatch):
    """Build a plausible MW4 install under a fake %LOCALAPPDATA%.

    Returns the two file paths so a test can assert against the bytes on disk.
    """
    players = tmp_path / "Activision" / "Call of Duty" / f"players{BUILD_TAG.upper()}"
    profile_dir = players / ACCOUNT_ID
    profile_dir.mkdir(parents=True)

    global_file = players / f"s.2.0.{BUILD_TAG}.cod26.txt"
    profile_file = profile_dir / f"g.{BUILD_TAG}.cod26.1.0.l.txt"
    global_file.write_bytes(GLOBAL_SAMPLE.encode("utf-8"))
    profile_file.write_bytes(PROFILE_SAMPLE.encode("utf-8"))

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return global_file, profile_file


class TestDiscovery:
    """C9: every moving segment of the path is found, never spelled."""

    def test_finds_both_files_under_an_unfamiliar_build_and_account(self, mw4_install):
        global_file, profile_file = mw4_install
        assert mw4_config_paths() == (global_file, profile_file)

    def test_beta_directory_name_is_matched_too(self, tmp_path, monkeypatch):
        players = tmp_path / "Activision" / "Call of Duty" / "playersBeta"
        (players / "1234").mkdir(parents=True)
        expected = players / "s.1.0.bt.cod26.txt"
        expected.write_bytes(GLOBAL_SAMPLE.encode("utf-8"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        assert mw4_config_paths()[0] == expected

    def test_the_pm_variant_is_not_mistaken_for_the_profile_file(self, mw4_install):
        """`g.<tag>.cod26.pm.1.0.l.txt` sits beside the real one and holds almost nothing."""
        _, profile_file = mw4_install
        decoy = profile_file.with_name(f"g.{BUILD_TAG}.cod26.pm.1.0.l.txt")
        decoy.write_bytes(b"1\n")
        os.utime(decoy, (10**9, 10**9))  # newer than the real file

        assert mw4_config_paths()[1] == profile_file

    def test_newest_wins_when_a_reinstall_leaves_two(self, mw4_install):
        global_file, _ = mw4_install
        older = global_file.with_name(f"s.1.0.{BUILD_TAG}.cod26.txt")
        older.write_bytes(GLOBAL_SAMPLE.encode("utf-8"))
        os.utime(older, (10**9, 10**9))
        os.utime(global_file, (2 * 10**9, 2 * 10**9))

        assert mw4_config_paths()[0] == global_file

    def test_absent_install_reports_nothing_rather_than_raising(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert mw4_config_paths() == (None, None)


@pytest.mark.usefixtures("scan_cache")
class TestReading:
    @pytest.mark.usefixtures("mw4_install")
    def test_reads_a_value_and_strips_the_trailing_comment(self):
        assert get_mw4_option("ResolutionMultiplier@0") == "50"

    @pytest.mark.usefixtures("mw4_install")
    def test_scope_index_selects_between_two_keys_of_the_same_name(self):
        """The whole point of keeping `@N`: same name, different ranges."""
        assert get_mw4_metadata("DxrMode@0")["choices"] == ("Off", "On")
        assert get_mw4_metadata("DxrMode@1")["choices"] == (
            "Off",
            "Low",
            "Medium",
            "High",
            "Ultra",
        )

    @pytest.mark.usefixtures("mw4_install")
    def test_key_containing_spaces_is_read(self):
        assert get_mw4_option("Sprint Assist Delay KBM@1", "profile") == "0"

    @pytest.mark.usefixtures("mw4_install")
    def test_empty_value_is_empty_not_missing(self):
        """An unset audio device is a real state; it is not an absent key."""
        assert get_mw4_option("VoiceOutputDevice@0") == ""

    @pytest.mark.usefixtures("mw4_install")
    def test_value_containing_a_colon_survives(self):
        assert get_mw4_option("RefreshRate@0") == "Auto:165.000"

    @pytest.mark.usefixtures("mw4_install")
    def test_missing_key_reports_not_installed(self):
        assert get_mw4_option("NoSuchSetting@0") == NOT_INSTALLED

    @pytest.mark.usefixtures("mw4_install")
    def test_key_without_a_scope_is_refused_rather_than_guessed(self):
        """`TextureQuality` alone is ambiguous the moment a second scope exists."""
        assert get_mw4_option("TextureQuality") == NOT_INSTALLED

    def test_absent_install_reports_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert get_mw4_option("TextureQuality@0") == NOT_INSTALLED

    @pytest.mark.usefixtures("mw4_install")
    def test_profile_source_does_not_read_the_global_file(self):
        assert get_mw4_option("TextureQuality@0", "profile") == NOT_INSTALLED

    @pytest.mark.usefixtures("mw4_install")
    def test_unknown_source_is_a_programming_error(self):
        with pytest.raises(ValueError, match="unknown MW4 config source"):
            get_mw4_option("TextureQuality@0", "savegame")


@pytest.mark.usefixtures("scan_cache")
class TestMetadataComesFromTheFile:
    @pytest.mark.usefixtures("mw4_install")
    def test_integer_range_stays_integer(self):
        """0..3, not 0.0..3.0 — a float would stop matching what the file holds."""
        meta = get_mw4_metadata("TextureQuality@0")
        assert meta == {"minimum": 0, "maximum": 3}
        assert isinstance(meta["maximum"], int)

    @pytest.mark.usefixtures("mw4_install")
    def test_float_range_stays_float(self):
        meta = get_mw4_metadata("VideoMemoryScaleMP@0")
        assert meta == {"minimum": 0.0, "maximum": 2.0}
        assert isinstance(meta["maximum"], float)

    @pytest.mark.usefixtures("mw4_install")
    def test_choices_keep_items_that_contain_separators(self):
        """`5:4` and `wide 16:9` must survive the comma split intact."""
        assert get_mw4_metadata("AspectRatio@0")["choices"] == (
            "auto",
            "standard",
            "5:4",
            "wide 16:9",
        )

    @pytest.mark.usefixtures("mw4_install")
    def test_a_key_without_a_comment_claims_no_range(self):
        """Absent metadata is absent authority — never a default range."""
        assert get_mw4_metadata("ConfigCloudStorageEnabled@0") == {}

    @pytest.mark.usefixtures("mw4_install")
    def test_texture_quality_range_is_read_not_assumed(self):
        """The scale is inverted (higher = lower resolution); the parser must not care.

        This guards the direction of the *code*, not the tweak: 0 is the top of
        the range, so a reader that treated `maximum` as "best" would recommend
        the worst texture quality in the game.
        """
        meta = get_mw4_metadata("TextureQuality@0")
        assert meta["minimum"] == 0 and meta["maximum"] == 3
        assert get_mw4_option("TextureQuality@0") == "1"


@pytest.mark.usefixtures("scan_cache")
class TestWriting:
    def test_changes_exactly_one_line_and_nothing_else(self, mw4_install):
        global_file, _ = mw4_install
        before = global_file.read_bytes()

        assert set_mw4_option("ResolutionMultiplier@0", "100") == "100"

        after = global_file.read_bytes()
        changed = [
            (b, a) for b, a in zip(before.split(b"\n"), after.split(b"\n"), strict=True) if b != a
        ]
        assert len(changed) == 1
        assert changed[0] == (
            b"ResolutionMultiplier@0;64786;30730 = 50 // 0 to 200",
            b"ResolutionMultiplier@0;64786;30730 = 100 // 0 to 200",
        )

    def test_preserves_lf_line_endings(self, mw4_install):
        global_file, _ = mw4_install
        set_mw4_option("TextureQuality@0", "0")
        assert b"\r\n" not in global_file.read_bytes()

    def test_does_not_introduce_a_bom(self, mw4_install):
        global_file, _ = mw4_install
        set_mw4_option("TextureQuality@0", "0")
        assert not global_file.read_bytes().startswith(codecs.BOM_UTF8)

    def test_preserves_a_bom_that_was_already_there(self, mw4_install):
        """Today's file has none, the release build may. Put back what was found."""
        global_file, _ = mw4_install
        global_file.write_bytes(codecs.BOM_UTF8 + GLOBAL_SAMPLE.encode("utf-8"))

        set_mw4_option("TextureQuality@0", "0")

        raw = global_file.read_bytes()
        assert raw.startswith(codecs.BOM_UTF8)
        assert raw.count(codecs.BOM_UTF8) == 1
        assert b"TextureQuality@0;61129;7764 = 0 // 0 to 3" in raw

    def test_writes_into_the_profile_file_when_told_to(self, mw4_install):
        _, profile_file = mw4_install
        assert set_mw4_option("AltShellShock@0", "true", "profile") == "true"
        assert b"AltShellShock@0;57752;48403 = true" in profile_file.read_bytes()

    def test_key_with_spaces_is_written(self, mw4_install):
        _, profile_file = mw4_install
        assert set_mw4_option("Sprint Assist Delay KBM@1", "250", "profile") == "250"
        assert b"Sprint Assist Delay KBM@1;23176;7764 = 250 // 0 to 12750" in (
            profile_file.read_bytes()
        )

    def test_writing_the_value_already_there_leaves_the_file_untouched(self, mw4_install):
        """mtime is how the newest-config glob picks a winner; do not disturb it."""
        global_file, _ = mw4_install
        os.utime(global_file, (10**9, 10**9))
        before = global_file.stat().st_mtime

        assert set_mw4_option("TextureQuality@0", "1") == "1"

        assert global_file.stat().st_mtime == before

    def test_a_read_only_file_is_unlocked_rather_than_failed(self, mw4_install):
        """An earlier fpstune release set this attribute on MW3 and broke saving."""
        global_file, _ = mw4_install
        global_file.chmod(0o444)

        assert set_mw4_option("TextureQuality@0", "0") == "0"
        assert b"TextureQuality@0;61129;7764 = 0" in global_file.read_bytes()

    def test_leaves_no_temp_file_behind(self, mw4_install):
        global_file, _ = mw4_install
        set_mw4_option("TextureQuality@0", "0")
        assert list(global_file.parent.glob("*.fpstune-tmp")) == []


@pytest.mark.usefixtures("scan_cache")
class TestTwoSettingsAppliedAtOnce:
    """One MW4 setting is a whole-file rewrite, and bulk apply runs sixteen.

    `api/routes/settings.py` applies settings in parallel through a
    ThreadPoolExecutor. Two threads writing this file both read it before either
    writes, so the second one rebuilds the file from a copy that never had the
    first one's change — and both report success, because each verifies against
    the copy it wrote itself. Apply green, verify green, setting gone.

    Measured on a real install 2026-08-24: `voice_volume` and `effects_volume`
    applied in the same second and collided on the shared temp path
    (`Permission denied`, `WinError 5`). The filesystem caught that pair only
    because both writers happened to choose the same temp name.
    """

    def _delay_reads_of(self, monkeypatch, target, seconds=0.3):
        """Hold every reader of one file open long enough to overlap.

        Without the lock both threads sit inside the read at the same moment,
        which is exactly the interleaving that loses an update. With the lock
        the second thread cannot start its read until the first has replaced
        the file, so the same delay simply serializes.
        """
        real_read = Path.read_bytes

        def slow_read(self):
            data = real_read(self)
            if self == target:
                time.sleep(seconds)
            return data

        monkeypatch.setattr(Path, "read_bytes", slow_read)

    def test_neither_setting_is_lost(self, mw4_install, monkeypatch):
        global_file, _ = mw4_install
        self._delay_reads_of(monkeypatch, global_file)

        failures: list[BaseException] = []

        def write(key: str, value: str) -> None:
            try:
                set_mw4_option(key, value)
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                failures.append(exc)

        threads = [
            threading.Thread(target=write, args=("TextureQuality@0", "0")),
            threading.Thread(target=write, args=("ResolutionMultiplier@0", "100")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert failures == []
        content = global_file.read_bytes()
        # Both, and with their hashes and range comments intact — a rebuild from
        # a stale copy would drop one of these two lines' new values.
        assert b"TextureQuality@0;61129;7764 = 0 // 0 to 3" in content
        assert b"ResolutionMultiplier@0;64786;30730 = 100 // 0 to 200" in content

    def test_the_lock_lets_one_writer_finish_before_the_next_starts(self):
        """The primitive itself, without a file: overlap is what must not happen."""
        events: list[str] = []

        def hold(name: str) -> None:
            with mw4_config._file_lock("global"):
                events.append(f"enter {name}")
                time.sleep(0.15)
                events.append(f"leave {name}")

        threads = [
            threading.Thread(target=hold, args=("a",)),
            threading.Thread(target=hold, args=("b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert len(events) == 4
        # Whichever went first, its leave precedes the other's enter.
        assert events[0].startswith("enter")
        assert events[1] == events[0].replace("enter", "leave")

    def test_the_two_config_files_do_not_block_each_other(self):
        """Separate files, separate locks — serializing them would halve bulk
        apply's throughput for a race that cannot happen between them."""
        with mw4_config._file_lock("global"):
            done = threading.Event()

            def take_the_other() -> None:
                with mw4_config._file_lock("profile"):
                    done.set()

            thread = threading.Thread(target=take_the_other)
            thread.start()
            thread.join(timeout=10)

        assert done.is_set(), "holding the global lock blocked the profile file"


@pytest.mark.usefixtures("scan_cache")
class TestWritingRefusesWhatTheGameWouldReject:
    @pytest.mark.usefixtures("mw4_install")
    def test_value_above_the_documented_range(self):
        with pytest.raises(Mw4ValueRejected, match="outside 0..3"):
            set_mw4_option("TextureQuality@0", "9")

    @pytest.mark.usefixtures("mw4_install")
    def test_value_not_in_the_documented_choices(self):
        with pytest.raises(Mw4ValueRejected, match="not one of"):
            set_mw4_option("AspectRatio@0", "wide 32:9")

    @pytest.mark.usefixtures("mw4_install")
    def test_non_numeric_where_a_number_is_required(self):
        with pytest.raises(Mw4ValueRejected, match="not numeric"):
            set_mw4_option("TextureQuality@0", "High")

    @pytest.mark.usefixtures("mw4_install")
    def test_the_two_scopes_enforce_their_own_ranges(self):
        """`Ultra` is valid for DxrMode@1 and invalid for DxrMode@0."""
        assert set_mw4_option("DxrMode@1", "Ultra") == "Ultra"
        with pytest.raises(Mw4ValueRejected, match="not one of"):
            set_mw4_option("DxrMode@0", "Ultra")

    def test_a_rejected_write_does_not_touch_the_file(self, mw4_install):
        global_file, _ = mw4_install
        before = global_file.read_bytes()
        with pytest.raises(Mw4ValueRejected):
            set_mw4_option("TextureQuality@0", "9")
        assert global_file.read_bytes() == before

    def test_case_is_normalised_to_the_files_own_spelling(self, mw4_install):
        """`ultra` passes a case-insensitive check, then loses to the game's parser."""
        global_file, _ = mw4_install
        assert set_mw4_option("DxrMode@1", "ultra") == "Ultra"
        assert b"DxrMode@1;8707;7764 = Ultra" in global_file.read_bytes()

    @pytest.mark.usefixtures("mw4_install")
    def test_a_key_without_a_range_comment_accepts_what_it_is_given(self):
        assert set_mw4_option("ConfigCloudStorageEnabled@0", "false") == "false"

    def test_missing_key_reports_not_installed_rather_than_appending(self, mw4_install):
        global_file, _ = mw4_install
        before = global_file.read_bytes()
        assert set_mw4_option("NoSuchSetting@0", "1") == NOT_INSTALLED
        assert global_file.read_bytes() == before

    def test_absent_install_reports_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert set_mw4_option("TextureQuality@0", "0") == NOT_INSTALLED


@pytest.mark.usefixtures("scan_cache")
class TestApplyThenDetectAgree:
    @pytest.mark.usefixtures("mw4_install")
    def test_a_write_is_visible_to_the_next_read_within_the_same_scan(self):
        """Apply is followed by a detect that reads the cache.

        Without the snapshot refresh the verify step compares the new value
        against the pre-apply cache and reports a mismatch fpstune created.
        """
        assert get_mw4_option("TextureQuality@0") == "1"
        set_mw4_option("TextureQuality@0", "0")
        assert get_mw4_option("TextureQuality@0") == "0"

    @pytest.mark.usefixtures("mw4_install")
    def test_the_snapshot_is_read_once_per_scan(self, monkeypatch):
        calls = {"n": 0}
        original = gcc._load_snapshot

        def counting():
            calls["n"] += 1
            return original()

        monkeypatch.setattr(gcc, "_load_snapshot", counting)
        get_mw4_option("TextureQuality@0")
        get_mw4_option("DxrMode@0")
        get_mw4_option("AltShellShock@0", "profile")
        assert calls["n"] == 1


class TestNonWindowsIsInert:
    def test_writer_reports_not_installed_off_windows(self, mw4_install, monkeypatch):
        monkeypatch.setattr(mw4_config.sys, "platform", "linux")
        global_file, _ = mw4_install
        before = global_file.read_bytes()

        assert set_mw4_option("TextureQuality@0", "0") == NOT_INSTALLED
        assert global_file.read_bytes() == before


@pytest.mark.usefixtures("scan_cache")
class TestNumbersKeepTheFilesOwnFormat:
    """MW4 stores decimals with six places. A UI slider sends `0.5`.

    Writing that verbatim leaves the config carrying two formats for the same
    kind of value, and a value that looks different from its neighbours reads as
    something fpstune got wrong.
    """

    def test_a_short_decimal_is_written_at_the_files_precision(self, mw4_install) -> None:
        global_file, _ = mw4_install
        global_file.write_bytes(
            b"1\nVideoMemoryScaleMP@0;59710;7707 = 0.750000 // 0.000000 to 2.000000\n"
        )

        assert set_mw4_option("VideoMemoryScaleMP@0", "0.5") == "0.500000"
        assert b"VideoMemoryScaleMP@0;59710;7707 = 0.500000" in global_file.read_bytes()

    def test_the_same_value_in_another_format_is_not_a_write(self, mw4_install) -> None:
        """`0.5` where the file holds `0.500000` is already there — rewriting it
        would move the mtime the newest-config glob depends on."""
        global_file, _ = mw4_install
        global_file.write_bytes(
            b"1\nVideoMemoryScaleMP@0;59710;7707 = 0.500000 // 0.000000 to 2.000000\n"
        )
        os.utime(global_file, (10**9, 10**9))
        before = global_file.stat().st_mtime

        assert set_mw4_option("VideoMemoryScaleMP@0", "0.5") == "0.500000"
        assert global_file.stat().st_mtime == before

    def test_an_integer_field_is_left_as_an_integer(self, mw4_install) -> None:
        global_file, _ = mw4_install
        assert set_mw4_option("TextureQuality@0", "0") == "0"
        assert b"TextureQuality@0;61129;7764 = 0 // 0 to 3" in global_file.read_bytes()

    @pytest.mark.parametrize(
        ("existing", "written"),
        [
            ("Auto:165.000", "Auto:240.000"),
            ("2560x1440", "1920x1080"),
            ("aniso 8x", "aniso 16x"),
        ],
    )
    def test_values_that_only_look_numeric_are_untouched(self, existing: str, written: str) -> None:
        """`Auto:300.000` contains a decimal and is not one."""
        from fpstune.settings.executors.mw4_config import _match_number_format

        assert _match_number_format(existing, written) == written

    def test_precision_follows_the_file_rather_than_a_constant(self) -> None:
        """A build that switches to three places should get three, not six."""
        from fpstune.settings.executors.mw4_config import _match_number_format

        assert _match_number_format("0.750", "0.5") == "0.500"
        assert _match_number_format("0.75", "0.5") == "0.50"
        assert _match_number_format("0.750000", "0.5") == "0.500000"


@pytest.mark.usefixtures("scan_cache")
class TestValueIsOneLine:
    """Issue #20: `_validate` only enforced a range when the key's own line
    carried one, so `RefreshRate@0` and `Resolution@0` — which carry no
    `// range` comment — were written verbatim, and a line break in the value
    spliced arbitrary extra keys into the game's config."""

    @pytest.mark.parametrize(
        "hostile",
        [
            "Auto:60.000\nAltShellShock@0 = true",
            "Auto:60.000\r\nAltShellShock@0 = true",
            "Auto:60.000\rAltShellShock@0 = true",
            "Auto:60.000\v60",
            "Auto:60.000\f60",
            "Auto:60.000\x1e60",
            "Auto:60.000\x8560",
            "Auto:60.000\u202860",
            "Auto:60.000\u202960",
        ],
    )
    def test_a_line_break_is_refused_for_a_key_with_no_declared_range(
        self, mw4_install, hostile: str
    ) -> None:
        global_file, _ = mw4_install
        before = global_file.read_bytes()

        with pytest.raises(Mw4ValueRejected):
            set_mw4_option("RefreshRate@0", hostile)

        assert global_file.read_bytes() == before

    def test_a_line_break_is_refused_for_a_key_that_does_declare_a_range(self, mw4_install) -> None:
        """The check runs before the metadata, so `0\n...` cannot pass as numeric."""
        global_file, _ = mw4_install
        before = global_file.read_bytes()

        with pytest.raises(Mw4ValueRejected):
            set_mw4_option("TextureQuality@0", "0\nAltShellShock@0 = true")

        assert global_file.read_bytes() == before

    def test_a_metadata_free_value_still_writes_when_it_is_one_line(self, mw4_install) -> None:
        """The point of the rule is structure, not authority: a key with no
        declared range must still accept the values it always did."""
        global_file, _ = mw4_install

        assert set_mw4_option("RefreshRate@0", "Auto:60.000") == "Auto:60.000"
        assert b"RefreshRate@0;56178;35888 = Auto:60.000" in global_file.read_bytes()

    def test_no_key_of_a_compound_is_written_when_one_value_is_multiline(self, mw4_install) -> None:
        from fpstune.settings.executors.mw4_config import set_mw4_options

        global_file, _ = mw4_install
        before = global_file.read_bytes()

        with pytest.raises(Mw4ValueRejected):
            set_mw4_options(["DxrMode@0", "DxrMode@1"], "Off\nAltShellShock@0 = true")

        assert global_file.read_bytes() == before

    def test_the_empty_value_is_not_a_line_break(self, mw4_install) -> None:
        """`VoiceOutputDevice@0` ships empty; refusing empty would break it."""
        global_file, _ = mw4_install

        assert set_mw4_option("VoiceOutputDevice@0", "") == ""
        assert b"VoiceOutputDevice@0;2059;35888 = \n" in global_file.read_bytes()
