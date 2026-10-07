"""SATA drives, through smartctl only when it is already on the machine.

The JSON keys are the ones `smartmontools/ataprint.cpp` emits for
`smartctl -j -A -l scttempsts`: `temperature.current`, and
`temperature.op_limit_max` only when the drive specifies a maximum operating
temperature greater than zero. What this file keeps true:

* the limit is the drive's *specified maximum operating temperature*, never SMART
  attribute 194's threshold, which is a normalised score and not a temperature;
* a drive that specifies no maximum is a gap, not a drive judged against a guess;
* no smartctl, or no administrator, is a named gap — never a silent nothing;
* a machine with no SATA drives never asks for smartctl at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from fpstune.health import smartctl
from fpstune.health.inventory import Disk
from fpstune.health.model import Gap
from fpstune.health.smartctl import NEEDS_ADMIN, NOT_INSTALLED, UNREADABLE, device_name, find, read
from fpstune.health.thermal import assess

_SSD = Disk(1, "5000C500A1B2C3D4", "CT500MX500SSD1", "SATA", "SSD")
_HDD = Disk(2, "5000C500DEADBEEF", "ST2000DM008-2FR102", "SATA", "HDD")
_NVME = Disk(0, "eui.0025385A11B2C3D4", "NVMe drive", "NVMe", "SSD")

# smartctl -j -A -l scttempsts on a SATA SSD that specifies a maximum operating temperature.
_WITH_LIMIT: dict[str, Any] = {
    "device": {"name": "/dev/sdb", "type": "sat", "protocol": "ATA"},
    "temperature": {
        "current": 38,
        "lifetime_min": 12,
        "lifetime_max": 61,
        "op_limit_max": 70,
        "under_limit_count": 0,
        "over_limit_count": 0,
    },
}
# A hard disk that reports a temperature through attribute 194 and no SCT maximum.
_WITHOUT_LIMIT: dict[str, Any] = {
    "device": {"name": "/dev/sdc", "type": "sat", "protocol": "ATA"},
    "temperature": {"current": 41},
    "ata_smart_attributes": {
        "table": [{"id": 194, "name": "Temperature_Celsius", "value": 59, "thresh": 0}]
    },
}


def _exe(tmp_path: Path) -> Path:
    exe = tmp_path / "smartctl.exe"
    exe.write_bytes(b"")
    return exe


def _runner(documents: dict[str, dict[str, Any] | None]):
    asked: list[str] = []

    def run(_exe: Path, device: str) -> dict[str, Any] | None:
        asked.append(device)
        return documents.get(device)

    run.asked = asked  # type: ignore[attr-defined]
    return run


class TestRead:
    def test_a_drive_against_its_specified_maximum_operating_temperature(
        self, tmp_path: Path
    ) -> None:
        run = _runner({"/dev/sdb": _WITH_LIMIT})

        snapshot = read([_SSD], exe=_exe(tmp_path), run=run, admin=True)

        (reading,) = snapshot.readings
        assert (reading.temperature_c, reading.limit_c) == (38.0, 70.0)
        assert reading.device_id == "5000C500A1B2C3D4"
        assert reading.component == "storage"
        assert assess([snapshot]).findings == ()

    def test_a_drive_close_to_that_maximum_is_a_warning(self, tmp_path: Path) -> None:
        hot = {"temperature": {"current": 66, "op_limit_max": 70}}

        snapshot = read([_SSD], exe=_exe(tmp_path), run=_runner({"/dev/sdb": hot}), admin=True)
        (finding,) = assess([snapshot]).findings

        assert (finding.severity, finding.title_key) == ("warning", "health.storage.temperature")

    def test_a_drive_that_specifies_no_maximum_is_a_gap_and_attribute_194_is_not_a_limit(
        self, tmp_path: Path
    ) -> None:
        snapshot = read(
            [_HDD], exe=_exe(tmp_path), run=_runner({"/dev/sdc": _WITHOUT_LIMIT}), admin=True
        )

        (reading,) = snapshot.readings
        assert (reading.temperature_c, reading.limit_c) == (41.0, None)
        result = assess([snapshot])
        assert result.findings == ()
        assert any(g.source == "smartctl" and "publishes no limit" in g.reason for g in result.gaps)

    def test_a_zero_maximum_is_the_same_as_none(self, tmp_path: Path) -> None:
        document = {"temperature": {"current": 41, "op_limit_max": 0}}

        snapshot = read([_HDD], exe=_exe(tmp_path), run=_runner({"/dev/sdc": document}), admin=True)

        assert snapshot.readings[0].limit_c is None

    def test_only_sata_drives_are_asked_and_by_the_name_smartctl_uses(self, tmp_path: Path) -> None:
        run = _runner({"/dev/sdb": _WITH_LIMIT, "/dev/sdc": _WITHOUT_LIMIT})

        read([_NVME, _SSD, _HDD], exe=_exe(tmp_path), run=run, admin=True)

        assert run.asked == ["/dev/sdb", "/dev/sdc"]  # type: ignore[attr-defined]

    def test_a_drive_that_answers_with_no_temperature_is_a_named_gap(self, tmp_path: Path) -> None:
        snapshot = read([_SSD], exe=_exe(tmp_path), run=_runner({"/dev/sdb": {}}), admin=True)

        assert snapshot.gaps == (Gap("smartctl", f"CT500MX500SSD1: {UNREADABLE}"),)

    def test_a_run_that_returned_nothing_parseable_is_a_named_gap(self, tmp_path: Path) -> None:
        snapshot = read([_SSD], exe=_exe(tmp_path), run=_runner({}), admin=True)

        assert snapshot.gaps == (Gap("smartctl", f"CT500MX500SSD1: {UNREADABLE}"),)


class TestWhenItCannotRun:
    def test_no_sata_drive_means_smartctl_is_never_looked_for(self) -> None:
        with patch.object(smartctl, "find", side_effect=AssertionError("looked")):
            snapshot = read([_NVME], admin=True)

        assert snapshot.gaps == () and snapshot.readings == ()

    def test_sata_drives_without_smartctl_are_one_gap_that_says_what_is_missing(self) -> None:
        with patch.object(smartctl, "find", return_value=None):
            snapshot = read([_SSD, _HDD], admin=True)

        assert snapshot.gaps == (Gap("smartctl", NOT_INSTALLED),)

    def test_without_administrator_it_is_a_named_gap_and_smartctl_is_not_run(
        self, tmp_path: Path
    ) -> None:
        run = _runner({"/dev/sdb": _WITH_LIMIT})

        snapshot = read([_SSD], exe=_exe(tmp_path), run=run, admin=False)

        assert snapshot.gaps == (Gap("smartctl", NEEDS_ADMIN),)
        assert run.asked == []  # type: ignore[attr-defined]


class TestFinding:
    def test_the_first_candidate_that_exists_wins(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope" / "smartctl.exe"
        present = _exe(tmp_path)

        assert find([missing, present]) == present

    def test_none_of_them_existing_is_none(self, tmp_path: Path) -> None:
        assert find([tmp_path / "a.exe", tmp_path / "b.exe"]) is None

    def test_it_looks_where_fpstune_keeps_tools_and_where_smartmontools_installs(
        self, tmp_path: Path
    ) -> None:
        with (
            patch.object(smartctl, "get_config_dir", return_value=tmp_path / "home"),
            patch.dict("os.environ", {"PROGRAMFILES": str(tmp_path / "pf")}),
        ):
            paths = smartctl.candidates()

        assert paths == [
            tmp_path / "home" / "tools" / "smartmontools" / "bin" / "smartctl.exe",
            tmp_path / "pf" / "smartmontools" / "bin" / "smartctl.exe",
        ]


class TestDeviceNames:
    def test_drive_zero_is_sda_and_drive_one_is_sdb(self) -> None:
        assert (device_name(0), device_name(1), device_name(25)) == (
            "/dev/sda",
            "/dev/sdb",
            "/dev/sdz",
        )

    def test_a_drive_number_smartctl_has_no_letter_for_is_not_guessed(self) -> None:
        assert device_name(26) is None and device_name(-1) is None
