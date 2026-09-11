""" "x8 of x16" is a lowered ceiling; "4" is not four gigatransfers.

Two ways this reading turns into a wrong number, and one way it turns into a
wrong machine.

*The link speed is an enumeration.* Windows answers `4` for a card running at
PCIe 4.0, which is 16 GT/s. Published as-is it would report a card on a quarter
of the link it has, and every comparison against it would be against a number
that means nothing.

*An adapter with no link is not an adapter at zero lanes.* An integrated GPU
returns empty for all four properties, because it is not on a PCIe link at all.
Read as zero it becomes the narrowest link on the machine, and a machine with an
iGPU would permanently report its graphics card as crippled.

*The widest link is the graphics card.* A capture card on x1 is a real PCIe
device with a real link, and taking the narrowest one would report its lane count
as the machine's ceiling.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from fpstune.benchmark.pcie_link import (
    LINK_SPEED_GTS,
    NO_LINK_DATA,
    PcieLinkBench,
    build_script,
)
from fpstune.benchmark.suite import Bench

# What this machine's two adapters answer, passed in as fixture input (C9). The
# discrete card reports all four; the integrated one reports empty strings.
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


def _adapter(**overrides: Any) -> dict[str, Any]:
    row = dict(_DISCRETE)
    row.update(overrides)
    return row


def _run(rows: list[dict[str, Any]], repeats: int = 2):
    with patch("fpstune.benchmark.pcie_link.query_rows", return_value=(rows, "")):
        return PcieLinkBench().run(repeats)


class TestTheEnumerationIsTranslated:
    def test_four_means_sixteen_gigatransfers(self) -> None:
        assert LINK_SPEED_GTS[4] == 16.0

    def test_the_reading_is_the_rate_and_not_the_enumeration(self) -> None:
        result = _run([_DISCRETE])

        assert result.readings["pcie_link_speed_gts"].median == pytest.approx(16.0)

    def test_an_enumeration_this_build_does_not_know_keeps_its_raw_value(self) -> None:
        """A generation newer than this table is not a rate we may invent."""
        result = _run([_adapter(current_speed=9, max_speed=9)])

        assert "pcie_link_speed_gts" not in result.readings
        assert result.detail["adapters"][0]["current_speed_enum"] == 9
        # The width is still a real reading, so the bench still ran.
        assert result.readings["pcie_link_width"].median == pytest.approx(16.0)


class TestWhichAdapterIsTheGraphicsCard:
    def test_an_integrated_adapter_is_not_a_link_of_zero_lanes(self) -> None:
        result = _run([_INTEGRATED, _DISCRETE])

        assert result.readings["pcie_link_width"].median == pytest.approx(16.0)
        assert len(result.detail["adapters"]) == 1

    def test_a_capture_card_on_one_lane_does_not_become_the_ceiling(self) -> None:
        narrow = _adapter(
            adapter="Capture device",
            instance_id="PCI\\VEN_1CFA&DEV_0000&SUBSYS_00000000&REV_01\\4&1A2B3C4D&0&0010",
            current_width=1,
            max_width=1,
        )

        result = _run([narrow, _DISCRETE])

        assert result.readings["pcie_link_width"].median == pytest.approx(16.0)

    def test_a_machine_with_no_pcie_adapter_at_all_says_so(self) -> None:
        result = _run([_INTEGRATED])

        assert not result.ran
        assert result.reason == NO_LINK_DATA


class TestALoweredCeilingIsSaidPlainly:
    def test_a_card_at_half_width_is_reported_as_such(self) -> None:
        """The C1 case: the ceiling was lowered before any setting was applied."""
        result = _run([_adapter(current_width=8, max_width=16)])

        assert result.detail["summary"].startswith("x8 of x16")
        assert result.detail["at_full_width"] is False

    def test_a_card_at_full_width_and_speed_says_that_too(self) -> None:
        result = _run([_DISCRETE])

        assert result.detail["summary"] == "x16 of x16, 16 GT/s of 16 GT/s"
        assert result.detail["at_full_width"] is True
        assert result.detail["at_full_speed"] is True

    def test_a_card_dropped_to_a_lower_generation_is_not_at_full_speed(self) -> None:
        result = _run([_adapter(current_speed=3, max_speed=4)])

        assert result.detail["at_full_speed"] is False
        assert "8 GT/s of 16 GT/s" in result.detail["summary"]

    def test_more_lanes_is_the_better_direction(self) -> None:
        """So a card that dropped to x8 between two runs reads as a regression."""
        assert _run([_DISCRETE]).readings["pcie_link_width"].improves_upward is True

    def test_each_adapter_keeps_its_own_instance_id(self) -> None:
        """C5: the id survives the card moving to another slot."""
        result = _run([_DISCRETE])

        assert result.detail["adapters"][0]["instance_id"] == _DISCRETE["instance_id"]


class TestTheQueryAndTheProtocol:
    def test_every_property_is_asked_for_in_one_call(self) -> None:
        """Per-key calls cost 7 s here against 0.7 s for the batch."""
        script = build_script()

        assert script.count("Get-PnpDeviceProperty") == 1
        for key in (
            "DEVPKEY_PciDevice_CurrentLinkWidth",
            "DEVPKEY_PciDevice_MaxLinkWidth",
            "DEVPKEY_PciDevice_CurrentLinkSpeed",
            "DEVPKEY_PciDevice_MaxLinkSpeed",
        ):
            assert key in script

    def test_a_failed_query_carries_its_own_reason(self) -> None:
        with patch(
            "fpstune.benchmark.pcie_link.query_rows",
            return_value=([], "Windows did not answer this query"),
        ):
            result = PcieLinkBench().run(2)

        assert not result.ran
        assert result.reason == "Windows did not answer this query"

    def test_it_satisfies_the_bench_protocol(self) -> None:
        assert isinstance(PcieLinkBench(), Bench)

    def test_it_declares_a_deadline_that_grows_with_repeats(self) -> None:
        bench = PcieLinkBench()

        assert bench.timeout_seconds(10) > bench.timeout_seconds(2)
