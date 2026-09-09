"""Tests for MW3's second config file: the per-account gamerprofile.

fpstune read only ``options.4.cod23.cst`` for a year — MW3's graphics file —
while audio, input, aim and field of view sat in a file it never opened. Three
things about that second file are ways to get it wrong on a machine other than
the developer's, and each has a class below:

* **The account directory is not unique and the filename is not fixed.** One
  install carries two of them, under different account ids and with different
  filenames, and a third-party fixer leaves stale copies under
  ``mw3fix_backup`` directories. First match wins is the wrong rule; newest
  mtime, backups excluded, is the rule the PowerShell writer of this same file
  already follows, and the two must agree or they write to different files.
* **Backups sit right next to the live file.** ``.cst0`` is a rolling text copy
  and ``.csb0``/``.csb1`` are binary stores. Only the ``.cst`` is written.
* **The line states its own range.** No range in this suite is asserted from a
  constant fpstune holds; every one is read out of the sample's own comments.

Nothing here touches a real install: every path is under ``tmp_path`` and every
account id is invented.
"""

from __future__ import annotations

import codecs
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.executors import game_config_cache as gcc
from fpstune.settings.executors import mw3_profile
from fpstune.settings.executors.game_config_cache import (
    NOT_INSTALLED,
    get_mw3_profile_metadata,
    get_mw3_profile_option,
    get_mw3_profile_options_agreed,
    mw3_profile_path,
)
from fpstune.settings.executors.mw3_profile import (
    Mw3ValueRejected,
    set_mw3_profile_option,
    set_mw3_profile_options,
)
from fpstune.settings.executors.powershell import PowerShellExecutor
from fpstune.settings.executors.ps_batch import init_scan_cache, reset_scan_cache

# Trimmed from a real cod23 gamerprofile, values changed. LF line endings and no
# BOM, like the file itself; the `// comment` on each line is the only statement
# of what the key accepts, so the tests read the ranges from here rather than
# declaring them.
PROFILE_SAMPLE = (
    "// Generated file, do not edit\n"
    "\n"
    "// KBM Advanced\n"
    "Sprint Assist Delay KBM@0 = 400 // 0 to 12750\n"
    "Sprint Assist Delay Gamepad@0 = 400 // 0 to 12750\n"
    "\n"
    "// Aim\n"
    "ADSSensitivity@0 = 0.850000 // 0.000000 to 8.000000\n"
    "ADSTimingSensitivity@0 = 2 // 0 to 2\n"
    "ADS2xZoomSensitivity@0 = 1.000000 // 0.000000 to 8.000000\n"
    "ADS4xZoomSensitivity@0 = 1.000000 // 0.000000 to 8.000000\n"
    "MouseAcceleration@0 = 0 // 0 to 1\n"
    "\n"
    "// Display\n"
    "Fov@0 = 100 // 60 to 120\n"
    "AimDownSightBehavior@0 = hold // one of hold, toggle\n"
    "VoiceOutputDevice@0 = \n"
    "SubtitlesEnabled@0 = false\n"
)

# Neither id belongs to anyone: one stands in for the Activision id the game
# uses and one for the Battle.net one, because a real install carries both.
ACCOUNT_ONE = "70000000001"
ACCOUNT_TWO = "1122334455667788"


@pytest.fixture
def scan_cache():
    _, token = init_scan_cache()
    yield
    reset_scan_cache(token)


@pytest.fixture
def documents(tmp_path, monkeypatch):
    """A Documents folder of our own, and no MW4 install beside it."""
    monkeypatch.setattr(gcc, "_documents_dir", lambda: tmp_path)
    # MW4 discovery runs in the same snapshot load; point it somewhere empty so
    # this suite never reads the machine it happens to run on.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty-local"))
    return tmp_path


@pytest.fixture
def mw3_install(documents):
    """One account directory holding the live gamerprofile.

    Returns its path so a test can assert against the bytes on disk.
    """
    profile_dir = documents / "Call of Duty MWIII" / "players" / ACCOUNT_ONE
    profile_dir.mkdir(parents=True)
    profile = profile_dir / "gamerprofile.0.BASE.cst"
    profile.write_bytes(PROFILE_SAMPLE.encode("utf-8"))
    return profile


class TestDiscovery:
    """C9: every moving segment of the path is found, never spelled."""

    def _profile(self, documents: Path, account: str, name: str, mtime: int) -> Path:
        path = documents / "Call of Duty MWIII" / "players" / account / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PROFILE_SAMPLE.encode("utf-8"))
        os.utime(path, (mtime, mtime))
        return path

    def test_finds_the_profile_under_an_unfamiliar_account_id(self, mw3_install):
        assert mw3_profile_path() == mw3_install

    def test_newest_of_two_accounts_wins(self, documents):
        """A real install carries two, under different ids and different names."""
        older = self._profile(documents, ACCOUNT_TWO, "gamerprofile.pc.0.BASE.cst", 1_000_000_000)
        newer = self._profile(documents, ACCOUNT_ONE, "gamerprofile.0.BASE.cst", 2_000_000_000)

        assert older.is_file(), "both candidates must exist for this to mean anything"
        assert mw3_profile_path() == newer

    def test_a_backup_copy_never_wins_however_new_it_is(self, documents):
        """The regression this rule exists for.

        A third-party fixer leaves copies under `mw3fix_backup*` directories. They
        are frequently the newest file on disk, and writing to one changes nothing
        for the game while apply and verify both report success — fpstune would be
        reading back its own write to a file MW3 never opens.
        """
        live = self._profile(documents, ACCOUNT_ONE, "gamerprofile.0.BASE.cst", 1_000_000_000)
        backup = self._profile(
            documents, "mw3fix_backup_2", "gamerprofile.0.BASE.cst", 3_000_000_000
        )
        nested = self._profile(
            documents, "mw3fix_backup", "gamerprofile.pc.0.BASE.cst", 4_000_000_000
        )

        assert backup.stat().st_mtime > live.stat().st_mtime
        assert nested.stat().st_mtime > live.stat().st_mtime
        assert mw3_profile_path() == live

    def test_the_rolling_and_binary_siblings_are_not_the_profile(self, mw3_install):
        """`.cst0` is a rolling text backup and `.csb0`/`.csb1` are binary stores."""
        for suffix in (".cst0", ".csb0", ".csb1"):
            sibling = mw3_install.parent / f"gamerprofile.0.BASE{suffix}"
            sibling.write_bytes(b"\x00\x01\x02")
            os.utime(sibling, (5_000_000_000, 5_000_000_000))

        assert mw3_profile_path() == mw3_install

    @pytest.mark.usefixtures("documents")
    def test_absent_install_reports_nothing_rather_than_raising(self):
        assert mw3_profile_path() is None

    def test_no_documents_folder_is_not_an_error(self, monkeypatch):
        monkeypatch.setattr(gcc, "_documents_dir", lambda: None)
        assert mw3_profile_path() is None


@pytest.mark.usefixtures("scan_cache")
class TestReading:
    @pytest.mark.usefixtures("mw3_install")
    def test_reads_a_value_and_strips_the_trailing_comment(self):
        assert get_mw3_profile_option("ADSSensitivity@0") == "0.850000"

    @pytest.mark.usefixtures("mw3_install")
    def test_key_containing_spaces_is_read(self):
        assert get_mw3_profile_option("Sprint Assist Delay KBM@0") == "400"

    @pytest.mark.usefixtures("mw3_install")
    def test_empty_value_is_empty_not_missing(self):
        """An unset audio device is a real state; it is not an absent key."""
        assert get_mw3_profile_option("VoiceOutputDevice@0") == ""

    @pytest.mark.usefixtures("mw3_install")
    def test_missing_key_reports_not_installed(self):
        assert get_mw3_profile_option("NoSuchSetting@0") == NOT_INSTALLED

    @pytest.mark.usefixtures("mw3_install")
    def test_key_without_a_scope_is_refused_rather_than_guessed(self):
        assert get_mw3_profile_option("ADSSensitivity") == NOT_INSTALLED

    @pytest.mark.usefixtures("documents")
    def test_absent_install_reports_not_installed(self):
        assert get_mw3_profile_option("ADSSensitivity@0") == NOT_INSTALLED

    @pytest.mark.usefixtures("mw3_install")
    def test_a_compound_reports_the_value_only_when_every_key_is_at_it(self):
        keys = ["ADS2xZoomSensitivity@0", "ADS4xZoomSensitivity@0"]
        assert get_mw3_profile_options_agreed(keys) == "1.000000"

        set_mw3_profile_option("ADS4xZoomSensitivity@0", "2.0")
        assert get_mw3_profile_options_agreed(keys) == "2.000000"

    @pytest.mark.usefixtures("mw3_install")
    def test_the_graphics_file_is_not_searched_for_a_profile_key(self):
        """MW3's two files are held apart: `mw3` is options.cst, `mw3_profile` is this."""
        assert gcc.get_mw3_option("ADSSensitivity") == NOT_INSTALLED


@pytest.mark.usefixtures("scan_cache", "mw3_install")
class TestMetadataComesFromTheFile:
    def test_integer_range_stays_integer(self):
        meta = get_mw3_profile_metadata("ADSTimingSensitivity@0")
        assert meta == {"minimum": 0, "maximum": 2}
        assert isinstance(meta["maximum"], int)

    def test_float_range_stays_float(self):
        meta = get_mw3_profile_metadata("ADSSensitivity@0")
        assert meta == {"minimum": 0.0, "maximum": 8.0}
        assert isinstance(meta["maximum"], float)

    def test_choices_are_read_from_the_line(self):
        assert get_mw3_profile_metadata("AimDownSightBehavior@0")["choices"] == ("hold", "toggle")

    def test_a_key_without_a_comment_claims_no_range(self):
        """Absent metadata is absent authority — never a default range."""
        assert get_mw3_profile_metadata("SubtitlesEnabled@0") == {}

    def test_the_fov_ceiling_is_the_files_own(self):
        """120 is what this file says, not a number fpstune holds."""
        assert get_mw3_profile_metadata("Fov@0") == {"minimum": 60, "maximum": 120}


@pytest.mark.usefixtures("scan_cache")
class TestWriting:
    def test_changes_one_line_and_keeps_its_range_comment(self, mw3_install):
        before = mw3_install.read_bytes()

        assert set_mw3_profile_option("Sprint Assist Delay KBM@0", "0") == "0"

        after = mw3_install.read_bytes()
        changed = [
            (b, a) for b, a in zip(before.split(b"\n"), after.split(b"\n"), strict=True) if b != a
        ]
        assert len(changed) == 1
        assert changed[0] == (
            b"Sprint Assist Delay KBM@0 = 400 // 0 to 12750",
            b"Sprint Assist Delay KBM@0 = 0 // 0 to 12750",
        )

    def test_preserves_lf_line_endings(self, mw3_install):
        set_mw3_profile_option("Fov@0", "120")
        assert b"\r\n" not in mw3_install.read_bytes()

    def test_does_not_introduce_a_bom(self, mw3_install):
        set_mw3_profile_option("Fov@0", "120")
        assert not mw3_install.read_bytes().startswith(codecs.BOM_UTF8)

    def test_preserves_a_bom_that_was_already_there(self, mw3_install):
        mw3_install.write_bytes(codecs.BOM_UTF8 + PROFILE_SAMPLE.encode("utf-8"))

        set_mw3_profile_option("Fov@0", "120")

        raw = mw3_install.read_bytes()
        assert raw.startswith(codecs.BOM_UTF8)
        assert raw.count(codecs.BOM_UTF8) == 1
        assert b"Fov@0 = 120 // 60 to 120" in raw

    def test_a_decimal_is_written_at_the_files_own_precision(self, mw3_install):
        """The file stores six places; a UI that sends `1` must not leave `1`."""
        assert set_mw3_profile_option("ADSSensitivity@0", "1") == "1.000000"
        assert b"ADSSensitivity@0 = 1.000000 // 0.000000 to 8.000000" in mw3_install.read_bytes()

    def test_writing_the_value_already_there_leaves_the_file_untouched(self, mw3_install):
        """mtime is how discovery picks between two accounts; do not disturb it."""
        os.utime(mw3_install, (10**9, 10**9))
        before = mw3_install.stat().st_mtime

        assert set_mw3_profile_option("ADSSensitivity@0", "0.85") == "0.850000"

        assert mw3_install.stat().st_mtime == before

    def test_a_read_only_file_is_unlocked_rather_than_failed(self, mw3_install):
        """An earlier fpstune release set this attribute on MW3's other config
        file, and the game could then persist nothing at all."""
        mw3_install.chmod(0o444)

        assert set_mw3_profile_option("Fov@0", "120") == "120"
        assert b"Fov@0 = 120" in mw3_install.read_bytes()

    def test_leaves_no_temp_file_behind(self, mw3_install):
        set_mw3_profile_option("Fov@0", "120")
        assert list(mw3_install.parent.glob("*.fpstune-tmp")) == []

    def test_a_backup_copy_is_never_the_file_that_gets_written(self, documents):
        """Discovery decides the target, so the write inherits the backup rule."""
        live_dir = documents / "Call of Duty MWIII" / "players" / ACCOUNT_ONE
        live_dir.mkdir(parents=True)
        live = live_dir / "gamerprofile.0.BASE.cst"
        live.write_bytes(PROFILE_SAMPLE.encode("utf-8"))
        os.utime(live, (10**9, 10**9))

        backup_dir = documents / "Call of Duty MWIII" / "players" / "mw3fix_backup"
        backup_dir.mkdir(parents=True)
        backup = backup_dir / "gamerprofile.0.BASE.cst"
        backup.write_bytes(PROFILE_SAMPLE.encode("utf-8"))
        os.utime(backup, (3 * 10**9, 3 * 10**9))

        assert set_mw3_profile_option("Fov@0", "120") == "120"

        assert b"Fov@0 = 120" in live.read_bytes()
        assert b"Fov@0 = 100" in backup.read_bytes(), "the backup must be left alone"

    def test_a_compound_writes_every_key_or_none(self, mw3_install):
        keys = ["ADS2xZoomSensitivity@0", "ADS4xZoomSensitivity@0"]
        assert set_mw3_profile_options(keys, "1.5") == "1.500000"

        content = mw3_install.read_bytes()
        assert b"ADS2xZoomSensitivity@0 = 1.500000 // 0.000000 to 8.000000" in content
        assert b"ADS4xZoomSensitivity@0 = 1.500000 // 0.000000 to 8.000000" in content


# The older of the two gamerprofile schemas, and it is still live: the second
# account directory on the same machine holds this shape while the first holds
# the one above. Same key names, same values, three differences that matter --
# no scope digit, no `=`, and a UTF-8 BOM in front of the first line.
#
# Nothing here is a variant fpstune invented. Discovery picks the newest file by
# modification time, so either schema can win on any given day, and a reader
# that only knows one of them makes every MW3 profile setting read absent and
# write nothing -- silently, which is the class of failure this project keeps
# paying for.
LEGACY_PROFILE_SAMPLE = (
    "// Generated file, do not edit\n"
    "\n"
    "// KBM Advanced\n"
    "Sprint Assist Delay KBM@ 400 // 0 to 12750\n"
    "Sprint Assist Delay Gamepad@ 400 // 0 to 12750\n"
    "\n"
    "// Aim\n"
    "ADSSensitivity@ 0.850000 // 0.100000 to 4.000000\n"
    "ADSTimingSensitivity@ 2 // 0 to 2\n"
    "MouseAcceleration@ 0.000000 // 0.000000 to 10.000000\n"
    "\n"
    "// Display\n"
    "Fov@ 100 // 60 to 120\n"
    "AimDownSightBehavior@ hold // one of hold, toggle\n"
    "SubtitlesEnabled@ false\n"
)


@pytest.fixture
def mw3_legacy_install(documents):
    """An install whose live profile carries the older, scope-less schema."""
    profile_dir = documents / "Call of Duty MWIII" / "players" / ACCOUNT_TWO
    profile_dir.mkdir(parents=True)
    profile = profile_dir / "gamerprofile.pc.0.BASE.cst"
    profile.write_bytes(codecs.BOM_UTF8 + LEGACY_PROFILE_SAMPLE.encode("utf-8"))
    return profile


def _key_names(sample: str) -> list[str]:
    """Every ``Name@`` key the sample declares, in file order."""
    import re

    return re.findall(r"(?m)^([^/\s][^@\n]*)@", sample)


@pytest.mark.usefixtures("scan_cache")
class TestTheOlderSchemaIsReadAndWrittenToo:
    """``Name@ value`` — no scope digit, no ``=``, and a BOM.

    Settings declare ``Name@0`` because that is what the current schema writes.
    The older file carries the same keys with the scope digit absent, so the
    MW3 matcher treats the digit as optional and accepts whitespace where the
    newer file puts ``=``. What comes back out has to be the line it went in
    as: ``Name@ `` stays ``Name@ ``, the range comment stays, the BOM stays.
    """

    def test_a_scopeless_line_is_read(self, mw3_legacy_install):
        assert mw3_legacy_install.is_file()
        assert get_mw3_profile_option("ADSSensitivity@0") == "0.850000"

    @pytest.mark.usefixtures("mw3_legacy_install")
    def test_a_key_containing_spaces_is_read(self):
        assert get_mw3_profile_option("Sprint Assist Delay KBM@0") == "400"

    @pytest.mark.usefixtures("mw3_legacy_install")
    def test_a_line_without_a_comment_is_still_a_value(self):
        assert get_mw3_profile_option("SubtitlesEnabled@0") == "false"

    @pytest.mark.usefixtures("mw3_legacy_install")
    def test_the_lines_own_comment_is_still_the_authority_on_the_range(self):
        assert get_mw3_profile_metadata("ADSSensitivity@0") == {"minimum": 0.1, "maximum": 4.0}
        assert get_mw3_profile_metadata("ADSTimingSensitivity@0") == {"minimum": 0, "maximum": 2}

    @pytest.mark.usefixtures("mw3_legacy_install")
    def test_choices_are_read_from_a_scopeless_line(self):
        assert get_mw3_profile_metadata("AimDownSightBehavior@0")["choices"] == ("hold", "toggle")

    @pytest.mark.usefixtures("mw3_legacy_install")
    def test_a_missing_key_still_reports_not_installed(self):
        assert get_mw3_profile_option("NoSuchSetting@0") == NOT_INSTALLED

    def test_a_write_changes_the_value_and_nothing_else_about_the_line(self, mw3_legacy_install):
        before = mw3_legacy_install.read_bytes()

        assert set_mw3_profile_option("Sprint Assist Delay KBM@0", "0") == "0"

        after = mw3_legacy_install.read_bytes()
        changed = [
            (b, a) for b, a in zip(before.split(b"\n"), after.split(b"\n"), strict=True) if b != a
        ]
        assert changed == [
            (
                b"Sprint Assist Delay KBM@ 400 // 0 to 12750",
                b"Sprint Assist Delay KBM@ 0 // 0 to 12750",
            )
        ]

    def test_the_bom_survives_the_write(self, mw3_legacy_install):
        set_mw3_profile_option("Fov@0", "120")

        raw = mw3_legacy_install.read_bytes()
        assert raw.startswith(codecs.BOM_UTF8)
        assert raw.count(codecs.BOM_UTF8) == 1
        assert b"Fov@ 120 // 60 to 120" in raw
        assert b"\r\n" not in raw

    def test_a_decimal_is_written_at_the_files_own_precision(self, mw3_legacy_install):
        assert set_mw3_profile_option("ADSSensitivity@0", "1") == "1.000000"
        assert b"ADSSensitivity@ 1.000000 // 0.100000 to 4.000000" in (
            mw3_legacy_install.read_bytes()
        )

    def test_a_value_the_line_forbids_is_still_refused(self, mw3_legacy_install):
        before = mw3_legacy_install.read_bytes()
        with pytest.raises(Mw3ValueRejected, match="outside 0..2"):
            set_mw3_profile_option("ADSTimingSensitivity@0", "3")
        assert mw3_legacy_install.read_bytes() == before

    @pytest.mark.usefixtures("mw3_legacy_install")
    def test_a_write_is_visible_to_the_next_read_within_the_same_scan(self):
        assert get_mw3_profile_option("Fov@0") == "100"
        set_mw3_profile_option("Fov@0", "120")
        assert get_mw3_profile_option("Fov@0") == "120"

    def test_neither_schema_repeats_a_key_name(self):
        """Why an optional scope digit is unambiguous rather than a guess.

        With the digit optional, ``Fov@0`` would match a scope-less ``Fov@``
        line whatever scope it belonged to. That is only safe because neither
        MW3 profile schema declares a name twice — unlike MW4, where
        ``DxrMode@0`` (Off/On) and ``DxrMode@1`` (Off..Ultra) are two different
        controls sharing a name, which is exactly why MW4's matcher still
        requires the digit.
        """
        for sample in (PROFILE_SAMPLE, LEGACY_PROFILE_SAMPLE):
            names = _key_names(sample)
            assert names, "the sample must declare keys for this to mean anything"
            assert len(names) == len(set(names)), sorted(names)

    @pytest.mark.usefixtures("mw3_install")
    def test_a_different_scope_digit_is_not_matched(self):
        """Optional is not "ignored" — a digit that is present must still agree."""
        assert get_mw3_profile_option("ADSSensitivity@1") == NOT_INSTALLED


class TestMw4sPatternIsNotWidened:
    """MW3's scope-less shape must not become MW4's.

    MW4's scope index is part of the key's identity: ``DxrMode@0`` is the
    Off/On master switch and ``DxrMode@1`` is the Off..Ultra quality level.
    Making the digit optional there would let one setting match the other's
    line and write it a value the game rejects.
    """

    def test_the_writer_still_requires_the_digit_for_mw4(self):
        from fpstune.settings.executors.game_config_writer import line_pattern

        pattern = line_pattern("DxrMode@0")
        assert pattern is not None
        assert pattern.search("DxrMode@ Off // one of Off, On") is None
        assert pattern.search("DxrMode@0;61129;7764 = Off // one of Off, On") is not None

    @pytest.mark.usefixtures("scan_cache")
    def test_the_mw4_reader_does_not_read_a_scopeless_line(self, tmp_path, monkeypatch):
        from fpstune.settings.executors.game_config_cache import get_mw4_option

        players = tmp_path / "Activision" / "Call of Duty" / "players"
        players.mkdir(parents=True)
        (players / "s.1.0.x.cod26.txt").write_bytes(b"1\nDxrMode@ Off // one of Off, On\n")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        assert get_mw4_option("DxrMode@0") == NOT_INSTALLED


@pytest.mark.usefixtures("scan_cache")
class TestWritingRefusesWhatTheGameWouldReject:
    def test_value_above_the_documented_range(self, mw3_install):
        before = mw3_install.read_bytes()
        with pytest.raises(Mw3ValueRejected, match="outside 0..2"):
            set_mw3_profile_option("ADSTimingSensitivity@0", "3")
        assert mw3_install.read_bytes() == before

    @pytest.mark.usefixtures("mw3_install")
    def test_value_not_in_the_documented_choices(self):
        with pytest.raises(Mw3ValueRejected, match="not one of"):
            set_mw3_profile_option("AimDownSightBehavior@0", "double tap")

    @pytest.mark.usefixtures("mw3_install")
    def test_non_numeric_where_a_number_is_required(self):
        with pytest.raises(Mw3ValueRejected, match="not numeric"):
            set_mw3_profile_option("Fov@0", "wide")

    def test_case_is_normalised_to_the_files_own_spelling(self, mw3_install):
        assert set_mw3_profile_option("AimDownSightBehavior@0", "TOGGLE") == "toggle"
        assert b"AimDownSightBehavior@0 = toggle" in mw3_install.read_bytes()

    @pytest.mark.parametrize(
        "hostile",
        [
            "120\nMouseAcceleration@0 = 1",
            "120\r\nMouseAcceleration@0 = 1",
            "120\rMouseAcceleration@0 = 1",
            "120 60",
        ],
    )
    def test_a_line_break_cannot_splice_a_second_key_in(self, mw3_install, hostile: str):
        before = mw3_install.read_bytes()
        with pytest.raises(Mw3ValueRejected):
            set_mw3_profile_option("Fov@0", hostile)
        assert mw3_install.read_bytes() == before

    def test_no_key_of_a_compound_is_written_when_the_value_is_refused(self, mw3_install):
        before = mw3_install.read_bytes()
        with pytest.raises(Mw3ValueRejected):
            set_mw3_profile_options(["ADS2xZoomSensitivity@0", "ADS4xZoomSensitivity@0"], "99")
        assert mw3_install.read_bytes() == before

    def test_missing_key_reports_not_installed_rather_than_appending(self, mw3_install):
        before = mw3_install.read_bytes()
        assert set_mw3_profile_option("NoSuchSetting@0", "1") == NOT_INSTALLED
        assert mw3_install.read_bytes() == before

    @pytest.mark.usefixtures("documents")
    def test_absent_install_reports_not_installed(self):
        assert set_mw3_profile_option("Fov@0", "120") == NOT_INSTALLED


@pytest.mark.usefixtures("scan_cache")
class TestApplyThenDetectAgree:
    @pytest.mark.usefixtures("mw3_install")
    def test_a_write_is_visible_to_the_next_read_within_the_same_scan(self):
        """Apply is followed by a detect that reads the per-scan snapshot.

        Without the refresh inside the lock, verify compares the new value
        against the pre-apply snapshot and reports a mismatch fpstune created.
        """
        assert get_mw3_profile_option("Fov@0") == "100"
        set_mw3_profile_option("Fov@0", "120")
        assert get_mw3_profile_option("Fov@0") == "120"

    @pytest.mark.usefixtures("mw3_install")
    def test_the_snapshot_is_read_once_per_scan(self, monkeypatch):
        calls = {"n": 0}
        original = gcc._load_snapshot

        def counting():
            calls["n"] += 1
            return original()

        monkeypatch.setattr(gcc, "_load_snapshot", counting)
        get_mw3_profile_option("Fov@0")
        get_mw3_profile_option("ADSSensitivity@0")
        get_mw3_profile_metadata("Fov@0")
        assert calls["n"] == 1


@pytest.mark.usefixtures("scan_cache")
class TestTwoSettingsAppliedAtOnce:
    """One profile setting is a whole-file rewrite, and bulk apply runs sixteen.

    Two threads writing this file both read it before either writes, so the
    second rebuilds the file from a copy that never had the first one's change —
    and both report success, because each verifies against the copy it wrote
    itself. Apply green, verify green, setting gone.
    """

    def _delay_reads_of(self, monkeypatch, target, seconds=0.3):
        real_read = Path.read_bytes

        def slow_read(self):
            data = real_read(self)
            if self == target:
                time.sleep(seconds)
            return data

        monkeypatch.setattr(Path, "read_bytes", slow_read)

    def test_neither_setting_is_lost(self, mw3_install, monkeypatch):
        self._delay_reads_of(monkeypatch, mw3_install)

        failures: list[BaseException] = []

        def write(key: str, value: str) -> None:
            try:
                set_mw3_profile_option(key, value)
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                failures.append(exc)

        threads = [
            threading.Thread(target=write, args=("Fov@0", "120")),
            threading.Thread(target=write, args=("MouseAcceleration@0", "1")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert failures == []
        content = mw3_install.read_bytes()
        assert b"Fov@0 = 120 // 60 to 120" in content
        assert b"MouseAcceleration@0 = 1 // 0 to 1" in content


class TestTheLockIsSharedWithThePowerShellWriterOfTheSameFile:
    """``mw3_texture_toggle`` rewrites this same gamerprofile from PowerShell.

    Two writers of one file that take *different* mutexes are two writers with
    no lock between them: each serializes only against itself, and the lost
    update the mutex exists to prevent comes straight back across the pair.
    """

    def test_the_mutex_name_is_the_one_the_powershell_group_uses(self):
        from fpstune.settings.executors.powershell_actions import _MUTEX_GROUPS

        assert mw3_profile._MUTEX_NAME in _MUTEX_GROUPS, (
            "the Python writer of the gamerprofile must take the same named mutex as "
            f"the PowerShell one; {sorted(_MUTEX_GROUPS)} does not contain it"
        )

    def test_it_is_not_mw4s_lock(self):
        """Separate files, separate locks — sharing would halve bulk apply's
        throughput for a race that cannot happen between them."""
        from fpstune.settings.executors.mw4_config import _MUTEX_NAMES

        assert mw3_profile._MUTEX_NAME not in _MUTEX_NAMES.values()

    def test_one_writer_finishes_before_the_next_starts(self):
        events: list[str] = []

        def hold(name: str) -> None:
            with mw3_profile._file_lock():
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
        assert events[0].startswith("enter")
        assert events[1] == events[0].replace("enter", "leave")


class TestTheRunningGameGuardCoversThisFileToo:
    """MW3 flushes its settings from memory on exit, so a write while it runs is
    undone minutes after apply and verify have both reported success. The guard
    is keyed on the setting id, and a profile setting carries the same
    ``game_config:mw3:`` prefix as the graphics ones — so it is covered without
    a second guard, which is what this pins."""

    def test_a_profile_setting_is_refused_while_mw3_runs(self, monkeypatch):
        from fpstune.settings.executors import game_processes

        monkeypatch.setattr(
            game_processes,
            "running_process_names",
            lambda **_: frozenset(game_processes.GAME_PROCESSES["mw3"]),
        )

        message = game_processes.refuse_if_game_is_running("game_config:mw3:ads_sensitivity")

        assert message is not None
        assert "Modern Warfare III" in message
        assert "Close the game and apply again" in message

    def test_nothing_is_refused_when_no_game_is_running(self, monkeypatch):
        from fpstune.settings.executors import game_processes

        monkeypatch.setattr(game_processes, "running_process_names", lambda **_: frozenset())

        assert game_processes.refuse_if_game_is_running("game_config:mw3:ads_sensitivity") is None


@pytest.mark.usefixtures("scan_cache")
class TestTheExecutorRoutesThisFile:
    """The end of the wire: a setting declaring `batch_config="mw3_profile"`
    detects, applies and detects again through `PowerShellExecutor`.

    Without a route the detect branch raises `unknown batch_config` and the
    apply branch falls through to PowerShell with an empty command — a setting
    that reads nothing and writes nothing while looking registered.
    """

    def _setting(self, key: object) -> SettingExecutor:
        return SettingExecutor(
            id="game_config:mw3:test_only_field_of_view",
            category=SettingCategory.GAME_CONFIG,
            display_name="Field of view",
            description="Test-only stand-in for a registered MW3 profile setting.",
            value_type=SettingValueType.INT,
            detect_type=DetectType.POWERSHELL,
            detect_args={"batch_config": "mw3_profile", "batch_key": key},
            apply_type=DetectType.POWERSHELL,
            apply_args={"batch_config": "mw3_profile", "batch_key": key},
        )

    def test_detect_reads_the_profile(self, mw3_install):
        assert mw3_install.is_file()
        value, error = PowerShellExecutor().detect(self._setting("Fov@0"))
        assert error is None
        assert value == "100"

    @pytest.mark.skipif(sys.platform != "win32", reason="the writer is inert off Windows")
    def test_apply_writes_it_and_the_next_detect_agrees(self, mw3_install):
        executor = PowerShellExecutor()
        setting = self._setting("Fov@0")

        ok, error = executor.apply(setting, "120")

        assert (ok, error) == (True, None)
        assert b"Fov@0 = 120 // 60 to 120" in mw3_install.read_bytes()
        assert executor.detect(setting) == ("120", None)

    @pytest.mark.skipif(sys.platform != "win32", reason="the writer is inert off Windows")
    def test_a_value_the_file_forbids_is_reported_not_written(self, mw3_install):
        before = mw3_install.read_bytes()

        ok, error = PowerShellExecutor().apply(self._setting("Fov@0"), "240")

        assert ok is False
        assert error is not None and "outside 60..120" in error
        assert mw3_install.read_bytes() == before

    @pytest.mark.usefixtures("documents")
    @pytest.mark.skipif(sys.platform != "win32", reason="the writer is inert off Windows")
    def test_an_absent_profile_is_named_rather_than_reported_as_a_write(self):
        ok, error = PowerShellExecutor().apply(self._setting("Fov@0"), "120")

        assert ok is False
        assert error == "Modern Warfare III profile config file not found"

    @pytest.mark.skipif(sys.platform != "win32", reason="the writer is inert off Windows")
    def test_a_compound_routes_every_key(self, mw3_install):
        keys = ["ADS2xZoomSensitivity@0", "ADS4xZoomSensitivity@0"]
        executor = PowerShellExecutor()
        setting = self._setting(keys)

        assert executor.apply(setting, "1.5") == (True, None)

        content = mw3_install.read_bytes()
        assert b"ADS2xZoomSensitivity@0 = 1.500000" in content
        assert b"ADS4xZoomSensitivity@0 = 1.500000" in content
        assert executor.detect(setting) == ("1.500000", None)


@pytest.mark.usefixtures("scan_cache")
class TestARegisteredSettingCompletesTheRoundTrip:
    """The wire end to end, for settings that actually ship.

    The class above proves the route with a stand-in built in the test. This one
    takes the registered definitions instead, so a key that is spelled wrong, a
    ``batch_config`` that names the other MW3 file, or a recommendation the
    line's own range forbids is caught here rather than on a user's machine.

    Verify is the same question the API asks after an apply: detect again, and
    compare with ``values_equal`` rather than ``==`` (C6).
    """

    def _setting(self, setting_id: str) -> SettingExecutor:
        from fpstune.settings.definitions.game_configs_mw3_profile import (
            MW3_PROFILE_SETTINGS,
        )

        return next(s for s in MW3_PROFILE_SETTINGS if s.id == setting_id)

    def test_detect_reads_the_value_the_file_holds(self, mw3_install):
        assert mw3_install.is_file()
        setting = self._setting("game_config:mw3:sprint_assist_delay_kbm")

        assert PowerShellExecutor().detect(setting) == ("400", None)
        assert values_equal("400", setting.default_value), (
            "the file's shipped value is what `reset` writes back, so a "
            "default_value that disagrees with it would undo to a state the "
            "game never had"
        )

    @pytest.mark.skipif(sys.platform != "win32", reason="the writer is inert off Windows")
    def test_apply_then_verify_agree_on_the_current_schema(self, mw3_install):
        executor = PowerShellExecutor()
        setting = self._setting("game_config:mw3:sprint_assist_delay_kbm")

        ok, error = executor.apply(setting, str(setting.recommended_value))

        assert (ok, error) == (True, None)
        assert b"Sprint Assist Delay KBM@0 = 0 // 0 to 12750" in mw3_install.read_bytes()
        detected, detect_error = executor.detect(setting)
        assert detect_error is None
        assert values_equal(detected, setting.recommended_value)

    @pytest.mark.skipif(sys.platform != "win32", reason="the writer is inert off Windows")
    def test_apply_then_verify_agree_on_the_older_schema(self, mw3_legacy_install):
        """The same registered setting, against the scope-less file."""
        executor = PowerShellExecutor()
        setting = self._setting("game_config:mw3:sprint_assist_delay_kbm")

        assert executor.detect(setting) == ("400", None)
        assert executor.apply(setting, str(setting.recommended_value)) == (True, None)

        raw = mw3_legacy_install.read_bytes()
        assert raw.startswith(codecs.BOM_UTF8)
        assert b"Sprint Assist Delay KBM@ 0 // 0 to 12750" in raw
        detected, detect_error = executor.detect(setting)
        assert detect_error is None
        assert values_equal(detected, setting.recommended_value)

    @pytest.mark.skipif(sys.platform != "win32", reason="the writer is inert off Windows")
    def test_a_named_compound_moves_every_zoom_level(self, mw3_install):
        """Six cvars, one concept — and the file only declares two of them here,
        which must still count as applied rather than as a failure."""
        executor = PowerShellExecutor()
        setting = self._setting("game_config:mw3:ads_zoom_sensitivity")

        assert executor.apply(setting, "1.5") == (True, None)
        content = mw3_install.read_bytes()
        assert b"ADS2xZoomSensitivity@0 = 1.500000" in content
        assert b"ADS4xZoomSensitivity@0 = 1.500000" in content

        assert executor.apply(setting, str(setting.recommended_value)) == (True, None)
        detected, _ = executor.detect(setting)
        assert values_equal(detected, setting.recommended_value)

    @pytest.mark.usefixtures("mw3_install")
    @pytest.mark.skipif(sys.platform != "win32", reason="the writer is inert off Windows")
    def test_the_guard_that_will_fire_on_a_real_install(self):
        """`ADSSensitivity` is a guard, and the profiles read held 0.850000.

        A guard whose recommendation equals the default is not dead weight: this
        is the drift it exists to notice and undo (product consequence 2).
        """
        executor = PowerShellExecutor()
        setting = self._setting("game_config:mw3:ads_sensitivity")

        detected, _ = executor.detect(setting)
        assert not values_equal(detected, setting.recommended_value)

        assert executor.apply(setting, str(setting.recommended_value)) == (True, None)
        detected, _ = executor.detect(setting)
        assert values_equal(detected, setting.recommended_value)


class TestNonWindowsIsInert:
    def test_writer_reports_not_installed_off_windows(self, mw3_install, monkeypatch):
        monkeypatch.setattr(mw3_profile.sys, "platform", "linux")
        before = mw3_install.read_bytes()

        assert set_mw3_profile_option("Fov@0", "120") == NOT_INSTALLED
        assert set_mw3_profile_options(["Fov@0"], "120") == NOT_INSTALLED
        assert mw3_install.read_bytes() == before
