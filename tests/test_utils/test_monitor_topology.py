"""The DeviceName → panel join, presence, and the report rows — as pure functions.

These cases were contract tests that ran the shipped PowerShell functions
``Build-DeviceHwIdMap`` and ``Split-MonitorPresence`` against described hosts.
The logic now lives in Python (``monitor_topology``), so the same hosts are
described here directly and the tests run without a PowerShell process.

The defects they exist for are unchanged: an order-based map that handed a 300 Hz
panel its 144 Hz neighbour's identity the moment a laptop's internal panel sorted
first; a present-but-inactive panel that vanished or shifted every other row;
detached heads carrying a stale path demoting a live panel.
"""

from __future__ import annotations

from fpstune.utils.monitor_topology import (
    WmiMonitorFacts,
    build_device_hwid_map,
    build_monitor_rows,
    parse_wmi_monitor_lines,
    split_monitor_presence,
)
from fpstune.utils.winapi.display import AdapterRecord, DisplayMode

# A laptop-shaped host. The internal panel carries the LOWEST UID and is not
# attached to the desktop (stateFlags 0); the 300 Hz external is the primary
# (flags 5 = attached | primary), the 144 Hz external is plain attached (1).
INTERNAL = {"uid": "1001", "hwId": "AAA0001"}
EXTERNAL_144 = {"uid": "5002", "hwId": "BBB0002"}
EXTERNAL_300 = {"uid": "9003", "hwId": "CCC0003"}

_GUID = "{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}"


def _rec(display: str, flags: int, hw_id: str, uid: str) -> AdapterRecord:
    return AdapterRecord(
        rf"\\.\{display}", flags, rf"\\?\DISPLAY#{hw_id}#4&1b2c3d4e&0&UID{uid}#{_GUID}"
    )


RECORDS = [
    _rec("DISPLAY1", 1, "BBB0002", "5002"),
    _rec("DISPLAY5", 5, "CCC0003", "9003"),
    _rec("DISPLAY2", 0, "AAA0001", "1001"),
]


def _uid_map(*panels: dict[str, str]) -> dict[str, str]:
    return {p["uid"]: p["hwId"] for p in panels}


def _presence(panels: list[dict[str, str]], records: list[AdapterRecord]) -> str:
    p = split_monitor_presence(records, _uid_map(*panels), [x["hwId"] for x in panels])
    attached = ";".join(
        f"{h.name}={h.hw_id},{h.primary}" for h in sorted(p.attached, key=lambda h: h.name)
    )
    inactive = ";".join(f"{i.name}={i.hw_id}" for i in sorted(p.inactive, key=lambda i: i.name))
    return f"A[{attached}] I[{inactive}]"


EXPECTED_MAP = {
    r"\\.\DISPLAY1": "BBB0002",
    r"\\.\DISPLAY2": "AAA0001",
    r"\\.\DISPLAY5": "CCC0003",
}


class TestTheJoinIsByIdentity:
    def test_every_screen_maps_to_its_own_panel(self) -> None:
        assert (
            build_device_hwid_map(RECORDS, _uid_map(INTERNAL, EXTERNAL_144, EXTERNAL_300))
            == EXPECTED_MAP
        )

    def test_wmi_order_cannot_change_the_map(self) -> None:
        """The gate: the exact property the deleted fallback violated."""
        for order in (
            [EXTERNAL_300, EXTERNAL_144, INTERNAL],
            [EXTERNAL_144, INTERNAL, EXTERNAL_300],
        ):
            assert build_device_hwid_map(RECORDS, _uid_map(*order)) == EXPECTED_MAP

    def test_screen_order_cannot_change_the_map_either(self) -> None:
        shuffled = [RECORDS[2], RECORDS[0], RECORDS[1]]
        assert (
            build_device_hwid_map(shuffled, _uid_map(INTERNAL, EXTERNAL_144, EXTERNAL_300))
            == EXPECTED_MAP
        )

    def test_the_previous_positional_zip_got_this_host_wrong(self) -> None:
        """Same host, joined the way the deleted fallback did: WMI sorted by UID
        (internal first) zipped against attached screens sorted by number. The
        300 Hz panel is handed its 144 Hz neighbour's identity."""
        wmi_by_uid = [
            p["hwId"]
            for p in sorted([INTERNAL, EXTERNAL_144, EXTERNAL_300], key=lambda p: int(p["uid"]))
        ]
        screens = sorted([r"\\.\DISPLAY1", r"\\.\DISPLAY5"])
        zipped = dict(zip(screens, wmi_by_uid, strict=False))
        assert zipped == {r"\\.\DISPLAY1": "AAA0001", r"\\.\DISPLAY5": "BBB0002"}
        assert zipped != {k: v for k, v in EXPECTED_MAP.items() if k in zipped}


class TestFailureStaysVisible:
    def test_an_unknown_uid_stays_unmapped(self) -> None:
        """A UID WMI never reported is a correlation failure, not a guess."""
        assert (
            build_device_hwid_map([_rec("DISPLAY7", 1, "ZZZ9999", "7777")], _uid_map(INTERNAL))
            == {}
        )

    def test_an_adapter_without_a_monitor_stays_unmapped(self) -> None:
        """An adapter head with nothing plugged in emits no interface path."""
        assert (
            build_device_hwid_map([AdapterRecord(r"\\.\DISPLAY3", 0, "")], _uid_map(INTERNAL)) == {}
        )


class TestAttachmentIsStateFlagsAnswer:
    def test_a_non_attached_head_is_inactive_not_active(self) -> None:
        """The gate: flags 0x0 is excluded from the active list and reported."""
        assert _presence([INTERNAL, EXTERNAL_144, EXTERNAL_300], RECORDS) == (
            r"A[\\.\DISPLAY1=BBB0002,False;\\.\DISPLAY5=CCC0003,True] I[\\.\DISPLAY2=AAA0001]"
        )

    def test_primary_comes_from_bit_two_not_from_position(self) -> None:
        """DISPLAY5 is primary here — any first-entry assumption reads DISPLAY1."""
        answer = _presence([EXTERNAL_144, EXTERNAL_300], RECORDS[:2])
        assert "DISPLAY5=CCC0003,True" in answer
        assert "DISPLAY1=BBB0002,False" in answer

    def test_a_mirroring_driver_is_no_panel(self) -> None:
        """Bit 3 marks a pseudo-device; attached or not, no user sees it."""
        mirror = [_rec("DISPLAYV1", 9, "BBB0002", "5002")]
        assert _presence([EXTERNAL_144], mirror) == "A[] I[BBB0002=BBB0002]"


class TestNothingPresentIsDropped:
    def test_a_wmi_only_panel_is_reported_present_but_inactive(self) -> None:
        """A panel WMI names with no head record at all still reaches the report."""
        assert _presence([INTERNAL, EXTERNAL_144], RECORDS[:1]) == (
            r"A[\\.\DISPLAY1=BBB0002,False] I[AAA0001=AAA0001]"
        )

    def test_an_attached_head_the_join_cannot_place_keeps_an_empty_hwid(self) -> None:
        """Correlation failure on an attached screen stays visible, never guessed."""
        stray = [_rec("DISPLAY7", 1, "ZZZ9999", "7777")]
        assert _presence([INTERNAL], stray) == r"A[\\.\DISPLAY7=,False] I[AAA0001=AAA0001]"


class TestOnePanelIsOnePanel:
    def test_several_detached_heads_carrying_one_panel_are_one_row(self) -> None:
        """Measured: an internal panel's UID shows up on every unused GPU head."""
        heads = [_rec(f"DISPLAY{n}", 0, "AAA0001", "1001") for n in (2, 3, 4)]
        assert _presence([INTERNAL], heads) == r"A[] I[\\.\DISPLAY2=AAA0001]"

    def test_a_stale_head_cannot_demote_a_panel_that_is_live_elsewhere(self) -> None:
        """A detached head keeps the last-known path of whatever was once on it;
        the panel it names may be rendering right now on another head."""
        records = [_rec("DISPLAY9", 0, "BBB0002", "5002"), RECORDS[0]]
        assert _presence([EXTERNAL_144], records) == r"A[\\.\DISPLAY1=BBB0002,False] I[]"


class TestTheWmiRecordsParse:
    def test_names_uids_edids_and_native_modes_are_keyed_for_the_join(self) -> None:
        stdout = (
            "WMI|CCC0003|9003|QUJD|Alienware AW2725DF\n"
            "WMI|AAA0001|1001||\n"
            "NATIVE|CCC0003|2560|1440\n"
            "garbage line\n"
            "NATIVE|BROKEN|x|y\n"
        )
        facts = parse_wmi_monitor_lines(stdout)
        assert facts.names == {"CCC0003": "Alienware AW2725DF", "AAA0001": ""}
        assert facts.uid_to_hwid == {"9003": "CCC0003", "1001": "AAA0001"}
        assert facts.uid_to_edid == {"9003": "QUJD"}
        assert facts.native == {"CCC0003": (2560, 1440)}

    def test_a_name_containing_the_separator_survives(self) -> None:
        """The friendly name is last for exactly this reason."""
        facts = parse_wmi_monitor_lines("WMI|DEL4265|42||Dell | U2722D\n")
        assert facts.names["DEL4265"] == "Dell | U2722D"


class TestTheRows:
    def _facts(self) -> WmiMonitorFacts:
        return WmiMonitorFacts(
            names={"CCC0003": "AW2725DF", "AAA0001": "Internal Panel"},
            native={"CCC0003": (2560, 1440), "AAA0001": (1920, 1200)},
            uid_to_hwid=_uid_map(INTERNAL, EXTERNAL_300),
            uid_to_edid={"9003": "QUJD"},
        )

    def test_attached_heads_read_their_modes_and_inactive_panels_read_none(self) -> None:
        modes = {r"\\.\DISPLAY5": DisplayMode(2560, 1440, 300)}
        rows = build_monitor_rows(
            self._facts(),
            [RECORDS[1], RECORDS[2]],
            lambda dev: modes.get(dev),
            lambda dev, w, h: 300 if (dev, w, h) == (r"\\.\DISPLAY5", 2560, 1440) else 0,
        )
        assert [r.name for r in rows] == [r"\\.\DISPLAY5", r"\\.\DISPLAY2"]
        active, inactive = rows
        assert (active.width, active.height, active.refresh_hz, active.max_refresh_hz) == (
            2560,
            1440,
            300,
            300,
        )
        assert active.primary is True and active.is_active is True
        assert active.friendly_name == "AW2725DF" and active.hardware_id == "CCC0003"
        assert active.edid_b64 == "QUJD"
        # No mode data is read for a panel that is not on the desktop.
        assert (inactive.width, inactive.height, inactive.refresh_hz, inactive.max_refresh_hz) == (
            0,
            0,
            0,
            0,
        )
        assert (inactive.native_width, inactive.native_height) == (1920, 1200)
        assert inactive.is_active is False and inactive.friendly_name == "Internal Panel"

    def test_an_uncorrelated_head_falls_back_to_its_display_number(self) -> None:
        rows = build_monitor_rows(
            WmiMonitorFacts(),
            [_rec("DISPLAY7", 1, "ZZZ9999", "7777")],
            lambda _dev: DisplayMode(1920, 1080, 60),
            lambda _dev, _w, _h: 0,
        )
        assert rows[0].friendly_name == "Display 7"
        assert rows[0].hardware_id == ""
        # Native falls back to the current mode, and max to the current rate.
        assert (rows[0].native_width, rows[0].native_height, rows[0].max_refresh_hz) == (
            1920,
            1080,
            60,
        )

    def test_primary_sorts_first_then_by_name(self) -> None:
        rows = build_monitor_rows(
            self._facts(),
            [RECORDS[0], RECORDS[1]],
            lambda _dev: DisplayMode(1920, 1080, 144),
            lambda _dev, _w, _h: 144,
        )
        # The two attached heads first, primary before the rest; the internal
        # panel WMI knows but no head carries follows as present-but-inactive.
        assert [r.name for r in rows] == [r"\\.\DISPLAY5", r"\\.\DISPLAY1", "AAA0001"]
        assert rows[2].is_active is False


class TestTheShippedModuleHasNoPositionalPath:
    def test_the_zip_its_inputs_and_the_compiled_class_are_gone(self) -> None:
        """A wrong map is worse than an empty one, and nothing is compiled at run time."""
        from pathlib import Path

        import fpstune.utils.detect

        source = Path(fpstune.utils.detect.__file__).read_text(encoding="utf-8")
        assert "$wmiHwIds" not in source
        assert "$screensByNum" not in source
        # The word survives in comments that record why the port happened; the
        # compile forms may not.
        for compile_form in (
            "Add-Type @'",
            "Add-Type -TypeDefinition",
            "Add-Type -AssemblyName",
            "DllImport",
        ):
            assert compile_form not in source, compile_form
        assert "EnumerateAdapters" not in source
        assert "enumerate_adapters()" in source
        assert "build_monitor_rows(" in source
