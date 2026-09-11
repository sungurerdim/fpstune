"""A drive's own counters, and the three ways of reading them backwards.

*Life remaining is not wear used.* `ssd_longevity` is a claim that goes up when
the setting works, and the counter reports the share already spent. Publishing
the spent share under that name would report a drive wearing out as a drive
getting healthier.

*The worst drive is the answer, not the average.* Two drives, one at 4% wear and
one at 80%, average to 42% — a figure describing neither, and reassuring about
the one that is nearly finished.

*A refusal is not a healthy machine.* The cmdlet answers `PermissionDenied`
unelevated (measured on the machine this was written on), and the bench has to
say "needs administrator" rather than "no drives report anything" — a reason a
user can act on, and the difference C11 rule 3 is about.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from fpstune.benchmark.storage_health import (
    NEEDS_ADMIN,
    NO_COUNTERS,
    StorageHealthBench,
)
from fpstune.benchmark.suite import Bench

# A drive that answers, in the shape the cmdlet returns. `UniqueId` is an
# EUI-64, which is what an NVMe reports; passing one in as fixture input is the
# opposite of reading this machine's own (C9's second exclusion).
_NVME: dict[str, Any] = {
    "unique_id": "eui.0025385A11B2C3D4",
    "media_type": "SSD",
    "bus_type": "NVMe",
    "size_bytes": 1_000_204_886_016,
    "wear": 4,
    "power_on_hours": 5123,
    "temperature": 41,
    "read_errors": 0,
    "write_errors": 0,
    "start_stop_cycles": 812,
}


def _drive(**overrides: Any) -> dict[str, Any]:
    row = dict(_NVME)
    row.update(overrides)
    return row


def _run(rows: list[dict[str, Any]], repeats: int = 2):
    with (
        patch("fpstune.benchmark.storage_health.is_admin", return_value=True),
        patch("fpstune.benchmark.storage_health.query_rows", return_value=(rows, "")),
    ):
        return StorageHealthBench().run(repeats)


class TestLongevityIsWhatIsLeft:
    def test_a_drive_at_four_percent_wear_has_ninety_six_left(self) -> None:
        """Published as remaining, because the claim it answers goes up.

        A setting claiming `ssd_longevity: high` is claiming the drive lasts
        longer. Measured as wear used, a drive lasting longer would show a
        *smaller* number and the verdict would read `contradicted`.
        """
        result = _run([_drive(wear=4)])

        assert result.readings["ssd_longevity"].median == pytest.approx(96.0)
        assert result.readings["ssd_longevity"].improves_upward is True

    def test_the_most_worn_drive_is_the_one_reported(self) -> None:
        """Averaging hides the drive that is nearly finished."""
        result = _run([_drive(wear=4), _drive(unique_id="eui.0025385A99887766", wear=80)])

        assert result.readings["ssd_longevity"].median == pytest.approx(20.0)

    def test_a_drive_that_reports_no_wear_does_not_read_as_unworn(self) -> None:
        """None and zero are different answers; only one is a measurement."""
        result = _run([_drive(wear=None)])

        assert "ssd_longevity" not in result.readings

    def test_the_hottest_drive_and_every_fault_are_reported(self) -> None:
        result = _run(
            [
                _drive(temperature=41, read_errors=0, write_errors=2),
                _drive(unique_id="eui.0025385A99887766", temperature=57, read_errors=3),
            ]
        )

        assert result.readings["storage_temp_c"].median == pytest.approx(57.0)
        assert result.readings["storage_error_count"].median == pytest.approx(5.0)


class TestAgeIsNotARegression:
    def test_power_on_hours_never_becomes_a_comparable_reading(self) -> None:
        """A drive gets older whatever fpstune does.

        Offered to `compare_runs`, a rising hour count would be reported as a
        change that beat the noise floor — a regression manufactured by the
        passage of time.
        """
        result = _run([_drive(power_on_hours=5123)])

        assert "power_on_hours" not in result.readings
        assert result.detail["drives"][0]["power_on_hours"] == 5123

    def test_each_drive_is_keyed_by_its_unique_id(self) -> None:
        """C5: the id survives the drive moving to another port."""
        result = _run([_drive(), _drive(unique_id="eui.0025385A99887766")])

        ids = [drive["unique_id"] for drive in result.detail["drives"]]
        assert ids == ["eui.0025385A11B2C3D4", "eui.0025385A99887766"]


class TestWhatItCannotRead:
    def test_an_unelevated_process_is_told_to_elevate(self) -> None:
        with patch("fpstune.benchmark.storage_health.is_admin", return_value=False):
            bench = StorageHealthBench()
            available, why = bench.is_available()
            result = bench.run(2)

        assert not available
        assert why == NEEDS_ADMIN
        assert not result.ran
        assert result.reason == NEEDS_ADMIN

    def test_a_machine_whose_drives_hide_their_counters_says_so(self) -> None:
        """Not the same sentence as the refusal, because it is not the same fix."""
        result = _run([])

        assert not result.ran
        assert result.reason == NO_COUNTERS

    def test_drives_that_answer_with_nothing_readable_produce_no_verdict(self) -> None:
        result = _run([_drive(wear=None, temperature=None, read_errors=None, write_errors=None)])

        assert not result.ran
        assert result.reason
        assert result.detail["drives"][0]["media_type"] == "SSD"

    def test_a_failed_query_carries_its_own_reason(self) -> None:
        with (
            patch("fpstune.benchmark.storage_health.is_admin", return_value=True),
            patch(
                "fpstune.benchmark.storage_health.query_rows",
                return_value=([], "Windows did not answer this query"),
            ),
        ):
            result = StorageHealthBench().run(2)

        assert not result.ran
        assert result.reason == "Windows did not answer this query"


class TestItIsABench:
    def test_it_satisfies_the_protocol(self) -> None:
        assert isinstance(StorageHealthBench(), Bench)

    def test_it_declares_a_deadline_that_grows_with_repeats(self) -> None:
        bench = StorageHealthBench()
        assert bench.timeout_seconds(6) > bench.timeout_seconds(2)

    def test_the_query_asks_every_physical_disk_for_its_counters(self) -> None:
        from fpstune.benchmark.storage_health import SCRIPT

        assert "Get-PhysicalDisk" in SCRIPT
        assert "Get-StorageReliabilityCounter" in SCRIPT
        assert "UniqueId" in SCRIPT
