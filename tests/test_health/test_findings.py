"""A healthy machine is an empty list, and a check that could not run is not healthy.

The findings module turns three instruments into one list, so the ways it can lie
are the ways a list can:

* a machine with nothing wrong must produce *nothing* — a finding per instrument
  "all good" would make a badge of "3 problems" on a clean machine;
* an instrument that could not run must say so beside the list — a drive health
  counter that needs administrator is a gap, never a drive in good health;
* one source that raises must not take the others down with it, and must not
  vanish either.

Every instrument here is run for real with its PowerShell query patched out, so the
fixtures are the rows the instrument's own script returns rather than hand-built
results that could drift from what it produces.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from fpstune.benchmark.event_scan import EventScanBench
from fpstune.benchmark.pcie_link import NO_LINK_DATA, PcieLinkBench
from fpstune.benchmark.storage_health import NEEDS_ADMIN, StorageHealthBench
from fpstune.benchmark.suite import BenchResult
from fpstune.health import findings as health
from fpstune.health.findings import (
    CACHE_SECONDS,
    TITLE_KEYS,
    WEAR_WARNING_MARGIN_PERCENT,
    Finding,
    Gap,
    Quantity,
    SourceResult,
    collect,
    event_findings,
    pcie_findings,
    reset_cache,
    stable_pci_id,
    storage_findings,
)

# An NVMe's own EUI-64 and a discrete + integrated adapter pair, passed in as
# fixture input (C9, second exclusion) in the shape each query returns.
_DRIVE: dict[str, Any] = {
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
_DISCRETE: dict[str, Any] = {
    "adapter": "NVIDIA GeForce RTX 3070 Laptop GPU",
    "instance_id": "PCI\\VEN_10DE&DEV_249D&SUBSYS_11471D05&REV_A1\\4&2BCAA58D&0&0008",
    "current_width": 16,
    "max_width": 16,
    "current_speed": 4,
    "max_speed": 4,
}
_INTEGRATED: dict[str, Any] = {
    "adapter": "Intel(R) UHD Graphics",
    "instance_id": "PCI\\VEN_8086&DEV_9A60&SUBSYS_11471D05&REV_01\\3&11583659&0&10",
    "current_width": "",
    "max_width": "",
    "current_speed": "",
    "max_speed": "",
}
_CLEAN_EVENTS: dict[str, Any] = {
    "whea": 0,
    "bugcheck": 0,
    "unexpected_shutdown": 0,
    "tdr": 0,
    "disk_errors": 0,
    "disk_providers": "",
    "log_from": 0,
}


def _storage(*drives: dict[str, Any]) -> BenchResult:
    with (
        patch("fpstune.benchmark.storage_health.is_admin", return_value=True),
        patch("fpstune.benchmark.storage_health.query_rows", return_value=(list(drives), "")),
    ):
        return StorageHealthBench().run(1)


def _pcie(*adapters: dict[str, Any]) -> BenchResult:
    with patch("fpstune.benchmark.pcie_link.query_rows", return_value=(list(adapters), "")):
        return PcieLinkBench().run(1)


def _events(dumps: int = 0, **overrides: Any) -> BenchResult:
    row = dict(_CLEAN_EVENTS)
    row.update(overrides)
    with (
        patch("fpstune.benchmark.event_scan.query_rows", return_value=([row], "")),
        patch("fpstune.benchmark.event_scan.minidump_count", return_value=dumps),
        patch("fpstune.benchmark.event_scan.baseline_started_at", return_value=None),
    ):
        return EventScanBench().run(1)


class TestStorage:
    def test_a_drive_with_most_of_its_life_left_is_not_a_finding(self) -> None:
        assert storage_findings(_storage(dict(_DRIVE))) == SourceResult()

    def test_the_margin_starts_a_warning_exactly_where_it_says(self) -> None:
        edge = 100.0 - WEAR_WARNING_MARGIN_PERCENT
        below = storage_findings(_storage(dict(_DRIVE, wear=edge - 1)))
        at = storage_findings(_storage(dict(_DRIVE, wear=edge)))

        assert below.findings == ()
        assert [f.severity for f in at.findings] == ["warning"]

    def test_a_drive_at_its_rated_endurance_is_critical_and_names_the_drive(self) -> None:
        result = storage_findings(_storage(dict(_DRIVE, wear=100)))

        assert result.findings == (
            Finding(
                component="storage",
                device_id="eui.0025385A11B2C3D4",
                severity="critical",
                title_key="health.storage.endurance",
                reading=Quantity(100.0, "%"),
                limit=Quantity(100.0, "%"),
                source="storage_health",
            ),
        )

    def test_the_spec_lets_wear_exceed_one_hundred_and_that_is_still_critical(self) -> None:
        result = storage_findings(_storage(dict(_DRIVE, wear=117)))

        assert [(f.severity, f.reading) for f in result.findings] == [
            ("critical", Quantity(117.0, "%"))
        ]

    def test_only_the_worn_drive_of_two_is_reported(self) -> None:
        worn = dict(_DRIVE, unique_id="eui.002538DEADBEEF01", wear=95)
        result = storage_findings(_storage(dict(_DRIVE), worn))

        assert [f.device_id for f in result.findings] == ["eui.002538DEADBEEF01"]

    def test_a_drive_that_reports_no_wear_figure_has_not_said_it_is_unworn(self) -> None:
        result = storage_findings(_storage(dict(_DRIVE, wear=None, temperature=40)))

        assert result.findings == ()

    def test_error_totals_alone_are_not_a_finding(self) -> None:
        """A SATA drive's raw error totals run to millions on a healthy disk."""
        result = storage_findings(_storage(dict(_DRIVE, read_errors=48_000_000, write_errors=12)))

        assert result.findings == ()

    def test_without_administrator_the_instrument_is_a_gap_not_a_clean_drive(self) -> None:
        with patch("fpstune.benchmark.storage_health.is_admin", return_value=False):
            result = storage_findings(StorageHealthBench().run(1))

        assert result.findings == ()
        assert result.gaps == (Gap(source="storage_health", reason=NEEDS_ADMIN),)


class TestPcie:
    def test_a_card_on_every_lane_it_has_is_not_a_finding(self) -> None:
        assert pcie_findings(_pcie(dict(_DISCRETE), dict(_INTEGRATED))) == SourceResult()

    def test_half_the_lanes_is_a_warning_with_the_card_and_both_numbers(self) -> None:
        result = pcie_findings(_pcie(dict(_DISCRETE, current_width=8)))

        assert result.findings == (
            Finding(
                component="gpu",
                device_id="PCI\\VEN_10DE&DEV_249D",
                severity="warning",
                title_key="health.gpu.pcie_link_width",
                reading=Quantity(8.0, "lanes"),
                limit=Quantity(16.0, "lanes"),
                source="pcie_link",
            ),
        )

    def test_a_slower_generation_at_full_width_is_the_idle_desktop_not_a_fault(self) -> None:
        """A card drops to the slowest generation when idle; flagging it is noise."""
        result = pcie_findings(_pcie(dict(_DISCRETE, current_speed=1)))

        assert result.findings == ()

    def test_an_integrated_adapter_alone_is_a_gap_with_the_instruments_reason(self) -> None:
        result = pcie_findings(_pcie(dict(_INTEGRATED)))

        assert result.findings == ()
        assert result.gaps == (Gap(source="pcie_link", reason=NO_LINK_DATA),)

    def test_the_id_is_the_stable_part_of_the_pnp_id(self) -> None:
        assert stable_pci_id(_DISCRETE["instance_id"]) == "PCI\\VEN_10DE&DEV_249D"
        assert stable_pci_id("pci\\ven_10de&dev_249d&subsys_x") == "PCI\\VEN_10DE&DEV_249D"
        assert stable_pci_id("") is None
        assert stable_pci_id("USB\\VID_046D&PID_C52B") is None


class TestEvents:
    def test_a_quiet_week_is_not_a_finding(self) -> None:
        assert event_findings(_events()) == SourceResult()

    def test_each_kind_lands_under_the_component_it_names_with_no_device(self) -> None:
        result = event_findings(
            _events(whea=3, tdr=2, disk_errors=5, unexpected_shutdown=1, bugcheck=1)
        )

        by_key = {f.title_key: f for f in result.findings}
        assert {k: (f.component, f.reading) for k, f in by_key.items()} == {
            "health.system.crashes": ("system", Quantity(1.0, "events")),
            "health.system.unexpected_shutdowns": ("system", Quantity(1.0, "events")),
            "health.system.hardware_errors": ("system", Quantity(3.0, "events")),
            "health.gpu.driver_resets": ("gpu", Quantity(2.0, "events")),
            "health.storage.io_errors": ("storage", Quantity(5.0, "events")),
        }
        assert all(f.device_id is None and f.limit is None for f in result.findings)
        assert all(f.severity == "warning" for f in result.findings)

    def test_one_bug_check_and_its_minidump_are_one_crash_not_two(self) -> None:
        result = event_findings(_events(dumps=1, bugcheck=1))

        assert [f.reading for f in result.findings] == [Quantity(1.0, "events")]

    def test_a_dump_with_error_reporting_off_is_still_a_crash(self) -> None:
        result = event_findings(_events(dumps=2, bugcheck=0))

        assert [f.reading for f in result.findings] == [Quantity(2.0, "events")]

    def test_a_log_that_could_not_be_read_is_a_gap_never_zero_crashes(self) -> None:
        with patch(
            "fpstune.benchmark.event_scan.query_rows",
            return_value=([], "Windows did not answer this query"),
        ):
            result = event_findings(EventScanBench().run(1))

        assert result.findings == ()
        assert [g.source for g in result.gaps] == ["event_scan"]


class TestTheFindingContract:
    def test_a_title_the_ui_has_no_string_for_cannot_be_built(self) -> None:
        with pytest.raises(ValueError, match="TITLE_KEYS"):
            Finding("gpu", None, "warning", "health.gpu.not_a_thing", None, None, "x")

    def test_every_title_is_namespaced_for_the_ui(self) -> None:
        assert all(key.startswith("health.") for key in TITLE_KEYS)


class TestCollect:
    @staticmethod
    def _finding(severity: str, component: str = "gpu", source: str = "a") -> Finding:
        return Finding(
            component,  # type: ignore[arg-type]
            None,
            severity,  # type: ignore[arg-type]
            "health.gpu.driver_resets",
            None,
            None,
            source,
        )

    def test_a_machine_with_nothing_wrong_yields_nothing(self) -> None:
        report = collect({"a": lambda: SourceResult(), "b": lambda: SourceResult()})

        assert report.findings == ()
        assert report.unmeasured == ()

    def test_critical_comes_before_warning_whatever_the_source_order(self) -> None:
        sources = {
            "first": lambda: SourceResult(findings=(self._finding("warning", source="first"),)),
            "second": lambda: SourceResult(findings=(self._finding("critical", source="second"),)),
        }

        report = collect(sources)

        assert [f.severity for f in report.findings] == ["critical", "warning"]

    def test_gaps_travel_beside_findings_and_are_never_counted_as_them(self) -> None:
        report = collect(
            {
                "drive": lambda: SourceResult(gaps=(Gap("drive", "needs administrator"),)),
                "gpu": lambda: SourceResult(findings=(self._finding("warning"),)),
            }
        )

        assert len(report.findings) == 1
        assert report.unmeasured == (Gap("drive", "needs administrator"),)

    def test_a_source_that_raises_becomes_a_named_gap_and_the_rest_still_answer(self) -> None:
        def broken() -> SourceResult:
            raise OSError("the event log is locked")

        report = collect(
            {"broken": broken, "ok": lambda: SourceResult(findings=(self._finding("warning"),))}
        )

        assert len(report.findings) == 1
        assert report.unmeasured == (Gap("broken", "the check failed (OSError)"),)

    def test_the_registry_names_the_three_instruments(self) -> None:
        assert set(health.SOURCES) >= {"storage_health", "pcie_link", "event_scan"}


class TestTheCache:
    @pytest.fixture(autouse=True)
    def _fresh_cache(self):
        reset_cache()
        yield
        reset_cache()

    def test_a_second_call_inside_the_window_does_not_ask_again(self) -> None:
        asked: list[int] = []

        def source() -> SourceResult:
            asked.append(1)
            return SourceResult()

        now = [100.0]
        with patch.dict(health.SOURCES, {"s": source}, clear=True):
            collect(clock=lambda: now[0])
            now[0] += CACHE_SECONDS - 1
            collect(clock=lambda: now[0])

        assert len(asked) == 1

    def test_after_the_window_it_asks_again(self) -> None:
        asked: list[int] = []

        def source() -> SourceResult:
            asked.append(1)
            return SourceResult()

        now = [100.0]
        with patch.dict(health.SOURCES, {"s": source}, clear=True):
            collect(clock=lambda: now[0])
            now[0] += CACHE_SECONDS
            collect(clock=lambda: now[0])

        assert len(asked) == 2

    def test_refresh_asks_again_immediately(self) -> None:
        asked: list[int] = []

        def source() -> SourceResult:
            asked.append(1)
            return SourceResult()

        with patch.dict(health.SOURCES, {"s": source}, clear=True):
            collect()
            collect(refresh=True)

        assert len(asked) == 2
