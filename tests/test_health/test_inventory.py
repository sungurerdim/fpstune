"""Which drives and adapters exist, parsed once and cached for a while.

The query returns one list with a `kind` column; what has to hold is that a disk with
an unreadable number is dropped rather than becoming drive 0, that the vendor comes from
the PCI id and not the marketing name, and that a *failed* read is never cached — a
transient PowerShell failure would otherwise blind the thermal readers for five minutes.
"""

from __future__ import annotations

from unittest.mock import patch

from fpstune.health import inventory as inv
from fpstune.health.inventory import CACHE_SECONDS, Disk, Inventory, inventory, parse, read

_ROWS = [
    {
        "kind": "disk",
        "number": "0",
        "unique_id": "eui.0025385A11B2C3D4",
        "name": "SAMSUNG MZVL21T0HCLR-00B00",
        "bus_type": "NVMe",
        "media_type": "SSD",
    },
    {
        "kind": "disk",
        "number": "1",
        "unique_id": "5000C500DEADBEEF",
        "name": "ST2000DM008-2FR102",
        "bus_type": "SATA",
        "media_type": "HDD",
    },
    {
        "kind": "adapter",
        "name": "Intel(R) UHD Graphics",
        "pnp": "PCI\\VEN_8086&DEV_9A60&SUBSYS_11471D05&REV_01\\3&11583659&0&10",
    },
    {
        "kind": "adapter",
        "name": "NVIDIA GeForce RTX 3070 Laptop GPU",
        "pnp": "PCI\\VEN_10DE&DEV_249D&SUBSYS_11471D05&REV_A1\\4&2BCAA58D&0&0008",
    },
]


class TestParse:
    def test_disks_and_adapters_come_apart_by_kind(self) -> None:
        result = parse(_ROWS)

        assert [(d.number, d.bus_type, d.unique_id) for d in result.disks] == [
            (0, "NVMe", "eui.0025385A11B2C3D4"),
            (1, "SATA", "5000C500DEADBEEF"),
        ]
        assert [a.stable_id for a in result.adapters] == [
            "PCI\\VEN_8086&DEV_9A60",
            "PCI\\VEN_10DE&DEV_249D",
        ]

    def test_the_vendors_come_from_the_pci_id(self) -> None:
        assert parse(_ROWS).vendors() == {"8086", "10DE"}

    def test_a_virtual_adapter_with_no_pci_id_has_no_vendor(self) -> None:
        rows = [
            {
                "kind": "adapter",
                "name": "Microsoft Basic Display",
                "pnp": "ROOT\\BasicDisplay\\0000",
            }
        ]

        assert parse(rows).vendors() == set()

    def test_a_disk_whose_number_is_not_a_number_is_dropped_not_made_drive_zero(self) -> None:
        rows = [dict(_ROWS[0], number="")]

        assert parse(rows).disks == ()

    def test_nothing_is_an_empty_inventory(self) -> None:
        assert parse([]) == Inventory()


class TestRead:
    def test_a_refused_query_carries_the_reason_and_no_lists(self) -> None:
        with patch.object(
            inv, "query_rows", return_value=([], "Windows did not answer this query")
        ):
            result = read()

        assert result.reason == "Windows did not answer this query"
        assert result.disks == () and result.adapters == ()


class TestTheCache:
    def setup_method(self) -> None:
        inv.reset_cache()

    def teardown_method(self) -> None:
        inv.reset_cache()

    @staticmethod
    def _counted(answer: Inventory):
        calls: list[int] = []

        def ask() -> Inventory:
            calls.append(1)
            return answer

        return ask, calls

    def test_it_is_asked_once_inside_the_window_and_again_after(self) -> None:
        ask, calls = self._counted(parse(_ROWS))
        now = [0.0]

        inventory(ask=ask, clock=lambda: now[0])
        now[0] = CACHE_SECONDS - 1
        inventory(ask=ask, clock=lambda: now[0])
        assert len(calls) == 1

        now[0] = CACHE_SECONDS + 1
        inventory(ask=ask, clock=lambda: now[0])
        assert len(calls) == 2

    def test_a_failed_read_is_not_cached(self) -> None:
        ask, calls = self._counted(Inventory(reason="Windows did not answer this query"))

        inventory(ask=ask, clock=lambda: 0.0)
        inventory(ask=ask, clock=lambda: 1.0)

        assert len(calls) == 2

    def test_a_disk_is_a_value_that_compares_by_content(self) -> None:
        assert Disk(0, "eui.1", "a", "NVMe", "SSD") == Disk(0, "eui.1", "a", "NVMe", "SSD")
