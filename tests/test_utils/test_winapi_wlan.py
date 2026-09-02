"""wlanapi through ctypes: the structs are the documented size, and the machine answers.

The C# class this replaces was compiled at run time inside a PowerShell command
(Add-Type), the pattern Windows Defender flagged on 2026-09-02. A struct one
byte off reads the wrong field for every user, silently, so the sizes are pinned
against the values the Windows SDK headers give.
"""

from __future__ import annotations

import ctypes
import sys

import pytest

from fpstune.utils.winapi import wlan
from fpstune.utils.winapi.wlan import (
    WLAN_BSS_ENTRY,
    WLAN_CONNECTION_ATTRIBUTES,
    WLAN_INTERFACE_INFO,
    WLAN_PROFILE_INFO,
    WlanRecord,
)


class TestStructLayouts:
    def test_interface_info_is_532_bytes(self) -> None:
        """GUID (16) + WCHAR[256] (512) + state (4): the item stride the list walk uses."""
        assert ctypes.sizeof(WLAN_INTERFACE_INFO) == 532

    def test_connection_attributes_is_604_bytes(self) -> None:
        """state + mode + WCHAR[256] + association (68, with its 2-byte pad after
        the BSSID) + security (16)."""
        assert ctypes.sizeof(WLAN_CONNECTION_ATTRIBUTES) == 604

    def test_bss_entry_is_360_bytes(self) -> None:
        """The SDK's sizeof(WLAN_BSS_ENTRY); the 8-byte timestamps force the padding."""
        assert ctypes.sizeof(WLAN_BSS_ENTRY) == 360

    def test_profile_info_is_516_bytes(self) -> None:
        assert ctypes.sizeof(WLAN_PROFILE_INFO) == 516


class TestRecordShape:
    def test_the_record_line_keeps_the_ssid_last(self) -> None:
        """An SSID may contain the separator; nothing after it needs splitting."""
        record = WlanRecord(
            interface_guid="aaaabbbb-cccc-dddd-eeee-ffff00001111",
            channel=1,
            center_khz=5955000,
            phy_type=10,
            signal_percent=84,
            auth_algorithm=9,
            ssid="cafe|guest",
            profile_name="cafe",
            bssid="00:11:22:33:44:55",
        )
        assert (
            record.as_record_line()
            == "aaaabbbb-cccc-dddd-eeee-ffff00001111|1|5955000|10|84|9|cafe|guest"
        )

    def test_guid_round_trip_is_lowercase_without_braces(self) -> None:
        raw = wlan._guid_bytes("{AAAABBBB-CCCC-DDDD-EEEE-FFFF00001111}")
        assert wlan._guid_str(bytes(raw)) == "aaaabbbb-cccc-dddd-eeee-ffff00001111"


@pytest.mark.skipif(sys.platform != "win32", reason="asks the running WLAN service")
class TestTheRealService:
    def test_interfaces_enumerate_without_error(self) -> None:
        """A machine with no Wi-Fi adapter answers with an empty list, not a crash."""
        result = wlan.interfaces()
        assert isinstance(result, list)
        for iface in result:
            assert len(iface.guid) == 36 and iface.guid == iface.guid.lower()

    def test_a_connected_radio_reports_numbers_not_words(self) -> None:
        records = wlan.query_connected()
        if not records:
            pytest.skip("no connected Wi-Fi radio on this machine")
        record = records[0]
        assert record.channel > 0
        assert 0 <= record.signal_percent <= 100
        assert record.phy_type > 0
        assert record.ssid

    def test_profiles_are_names_from_the_api(self) -> None:
        ifaces = wlan.interfaces()
        if not ifaces:
            pytest.skip("no Wi-Fi interface on this machine")
        names = wlan.profile_names(ifaces[0].guid)
        assert isinstance(names, list)
        assert all(isinstance(n, str) and n for n in names)
