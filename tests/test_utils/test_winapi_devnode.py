"""Device-node reads: the pure decoding, and the live calls against this machine.

The live tests are read-only and skip when the machine has nothing to read (no display
device present, no adapter with an interface index).
"""

from __future__ import annotations

import sys

import pytest

from fpstune.utils.winapi.devnode import decode_string_property, split_multi_sz
from fpstune.utils.winapi.netluid import split_luid


def test_a_string_property_is_utf16_up_to_its_first_nul() -> None:
    assert decode_string_property("oem9.inf\x00".encode("utf-16-le")) == "oem9.inf"
    assert decode_string_property("Section057\x00junk".encode("utf-16-le")) == "Section057"
    assert decode_string_property(b"") == ""


def test_a_multi_sz_buffer_is_its_non_empty_strings() -> None:
    assert split_multi_sz("PCI\\A\x00PCI\\B\x00\x00") == ["PCI\\A", "PCI\\B"]
    assert split_multi_sz("\x00") == []


def test_a_luid_splits_into_its_index_and_interface_type() -> None:
    # NetLuidIndex 32773 (0x8005), IfType 6 (ethernet), as in a real adapter's driver key.
    luid = (6 << 48) | (32773 << 24)
    assert split_luid(luid) == (32773, 6)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
class TestAgainstThisMachine:
    def test_a_present_display_device_is_bound_to_an_inf_section(self) -> None:
        from fpstune.utils.winapi.devnode import CLASS_DISPLAY, driver_inf, present_device_ids

        devices = present_device_ids(CLASS_DISPLAY)
        if not devices:
            pytest.skip("no display device is present")
        binding = driver_inf(devices[0])
        assert binding is not None
        assert binding.path.lower().endswith(".inf")
        assert binding.section

    def test_an_instance_id_the_system_has_never_seen_has_no_binding(self) -> None:
        from fpstune.utils.winapi.devnode import driver_inf

        assert driver_inf(r"PCI\VEN_FFFF&DEV_FFFF\NOT_A_DEVICE") is None

    def test_the_loopback_interface_index_is_not_an_adapter_with_a_driver_key(self) -> None:
        from fpstune.utils.winapi.netluid import adapter_instance_id

        # An index no machine has: no LUID, so no instance id and no exception.
        assert adapter_instance_id(0x7FFFFFFF) is None
