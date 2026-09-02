"""Which panels exist, which heads carry them, and what each one runs — as data.

WMI answers identity: a panel's hardware id, the UID Windows gave its instance,
its friendly name, the EDID it handed the OS and the modes it lists.
``EnumDisplayDevices`` answers the desktop: which adapter head is attached,
which is primary, and the interface path — whose UID segment is the same number
``WmiMonitorID.InstanceName`` carries. This module joins the two.

Everything here is a pure function over records, so the join the ceilings hang
from can be proven against described hosts without PowerShell. Two rules are
load-bearing and each has a test:

* **The join is by UID, never by position.** Zipping two independently sorted
  lists handed a panel its neighbour's mode table the moment a laptop's
  internal panel sorted first. A head the join cannot place keeps an empty
  hardware id — visible and reportable, where a plausible wrong map reports
  success.
* **Presence is StateFlags' answer, not WMI's.** WMI reports ``Active=True`` for
  a panel that is not on the desktop. Bit 0 is attachment, bit 2 primary, bit 3
  a mirroring pseudo-device that renders nothing. A panel WMI knows that no
  attached head carries is present-but-inactive — reported, never dropped.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from fpstune.utils.winapi.display import AdapterRecord, DisplayMode

_UID = re.compile(r"UID(\d+)")
_DISPLAY_NUMBER = re.compile(r"DISPLAY(\d+)")

CurrentModeReader = Callable[[str], DisplayMode | None]
MaxRefreshReader = Callable[[str, int, int], int]


@dataclass
class WmiMonitorFacts:
    """What WMI said about the panels, keyed the way the join needs it."""

    names: dict[str, str] = field(default_factory=dict)  # hwId -> friendly name
    native: dict[str, tuple[int, int]] = field(default_factory=dict)  # hwId -> (w, h)
    uid_to_hwid: dict[str, str] = field(default_factory=dict)
    uid_to_edid: dict[str, str] = field(default_factory=dict)  # uid -> base64 EDID


def parse_wmi_monitor_lines(stdout: str) -> WmiMonitorFacts:
    """Decode the ``WMI|hwId|uid|edidB64|name`` and ``NATIVE|hwId|w|h`` records.

    Positional and locale-free: numbers and base64 only, the friendly name last
    because a name may contain the separator. A row that does not parse is
    skipped rather than allowed to poison the join.
    """
    facts = WmiMonitorFacts()
    for raw in stdout.splitlines():
        line = raw.strip()
        if line.startswith("WMI|"):
            parts = line.split("|", 4)
            if len(parts) < 5:
                continue
            _, hw_id, uid, edid_b64, name = parts
            if not hw_id:
                continue
            facts.names[hw_id] = name.strip()
            if uid:
                facts.uid_to_hwid[uid] = hw_id
                if edid_b64:
                    facts.uid_to_edid[uid] = edid_b64
        elif line.startswith("NATIVE|"):
            parts = line.split("|")
            if len(parts) != 4:
                continue
            try:
                width, height = int(parts[2]), int(parts[3])
            except ValueError:
                continue
            if parts[1] and width > 0 and height > 0:
                facts.native[parts[1]] = (width, height)
    return facts


def _uid_of(record: AdapterRecord) -> str:
    match = _UID.search(record.monitor_interface_path)
    return match.group(1) if match else ""


def build_device_hwid_map(
    records: list[AdapterRecord], uid_to_hwid: dict[str, str]
) -> dict[str, str]:
    """``\\\\.\\DISPLAYn`` -> hardware id, joined by the UID in the interface path."""
    mapping: dict[str, str] = {}
    for record in records:
        uid = _uid_of(record)
        if uid and uid in uid_to_hwid:
            mapping[record.device_name] = uid_to_hwid[uid]
    return mapping


@dataclass(frozen=True)
class AttachedHead:
    name: str
    hw_id: str
    uid: str
    primary: bool


@dataclass(frozen=True)
class InactivePanel:
    name: str
    hw_id: str
    uid: str = ""


@dataclass(frozen=True)
class Presence:
    attached: list[AttachedHead]
    inactive: list[InactivePanel]


def split_monitor_presence(
    records: list[AdapterRecord], uid_to_hwid: dict[str, str], wmi_all_hwids: list[str]
) -> Presence:
    """Attached heads and present-but-inactive panels, from StateFlags.

    Attached first, so a detached head still carrying the last-known path of a
    panel that is live on another head cannot demote that panel to inactive. A
    detached head is only evidence of a panel no attached head accounts for —
    and several detached heads carrying the same panel are one panel, not
    three (measured: an internal panel's UID shows up on every unused GPU head).
    """
    mapping = build_device_hwid_map(records, uid_to_hwid)
    parsed = [r for r in records if not r.mirroring]

    attached: list[AttachedHead] = []
    inactive: list[InactivePanel] = []
    seen: set[str] = set()
    for record in parsed:
        if record.attached:
            hw_id = mapping.get(record.device_name, "")
            attached.append(
                AttachedHead(record.device_name, hw_id, _uid_of(record), record.primary)
            )
            if hw_id:
                seen.add(hw_id)
    for record in parsed:
        hw_id = mapping.get(record.device_name, "")
        if not record.attached and hw_id and hw_id not in seen:
            inactive.append(InactivePanel(record.device_name, hw_id, _uid_of(record)))
            seen.add(hw_id)
    for hw_id in wmi_all_hwids:
        if hw_id not in seen:
            inactive.append(InactivePanel(hw_id, hw_id))
            seen.add(hw_id)
    return Presence(attached=attached, inactive=inactive)


@dataclass(frozen=True)
class MonitorRow:
    """One line of the monitor report, before EDID decoding and the inclusion rule."""

    name: str
    width: int
    height: int
    refresh_hz: int
    primary: bool
    native_width: int
    native_height: int
    max_refresh_hz: int
    friendly_name: str
    hardware_id: str
    is_active: bool
    edid_b64: str


def _display_number(device_name: str) -> str:
    match = _DISPLAY_NUMBER.search(device_name)
    return match.group(1) if match else "?"


def build_monitor_rows(
    facts: WmiMonitorFacts,
    records: list[AdapterRecord],
    current_mode: CurrentModeReader,
    max_refresh_at: MaxRefreshReader,
) -> list[MonitorRow]:
    """Attached heads first (primary, then by name), then present-but-inactive panels.

    No mode data is read for a panel that is not on the desktop — 0 means "the
    panel did not say" and must stay 0 (``settings/panel.py``'s rule).
    """
    presence = split_monitor_presence(records, facts.uid_to_hwid, list(facts.names))
    rows: list[MonitorRow] = []

    for head in sorted(presence.attached, key=lambda h: (not h.primary, h.name)):
        mode = current_mode(head.name)
        cur_w, cur_h, cur_hz = (mode.width, mode.height, mode.refresh_hz) if mode else (0, 0, 0)
        native_w, native_h = facts.native.get(head.hw_id, (0, 0)) if head.hw_id else (0, 0)
        if native_w == 0:
            native_w = cur_w
        if native_h == 0:
            native_h = cur_h
        max_hz = max_refresh_at(head.name, native_w, native_h) if native_w and native_h else 0
        if max_hz <= 0:
            max_hz = cur_hz
        friendly = facts.names.get(head.hw_id, "") if head.hw_id else ""
        if not friendly:
            friendly = f"Display {_display_number(head.name)}"
        rows.append(
            MonitorRow(
                name=head.name,
                width=cur_w,
                height=cur_h,
                refresh_hz=cur_hz,
                primary=head.primary,
                native_width=native_w,
                native_height=native_h,
                max_refresh_hz=max_hz,
                friendly_name=friendly,
                hardware_id=head.hw_id,
                is_active=True,
                edid_b64=facts.uid_to_edid.get(head.uid, "") if head.uid else "",
            )
        )

    for panel in presence.inactive:
        native_w, native_h = facts.native.get(panel.hw_id, (0, 0)) if panel.hw_id else (0, 0)
        friendly = facts.names.get(panel.hw_id, "") if panel.hw_id else ""
        rows.append(
            MonitorRow(
                name=panel.name,
                width=0,
                height=0,
                refresh_hz=0,
                primary=False,
                native_width=native_w,
                native_height=native_h,
                max_refresh_hz=0,
                friendly_name=friendly or panel.name,
                hardware_id=panel.hw_id,
                is_active=False,
                edid_b64=facts.uid_to_edid.get(panel.uid, "") if panel.uid else "",
            )
        )
    return rows
