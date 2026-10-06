"""Every monitor at its own native resolution and its own maximum refresh rate.

The Hardware page could already fix one monitor at a time, but it was a button,
not a setting: Home never listed a secondary monitor left at 60 Hz, nothing put
the fix in a bulk apply, and nothing recorded it. Here it becomes one setting per
connected monitor (`definitions.display.create_monitor_mode_setting`), whose
detect and apply are the Python functions below, and the guarded write the
button used lives here so the button and the setting share it.

A display mode write is guarded twice, because a wrong mode on a machine nobody
is watching is a black screen nobody can debug:

1. CDS_TEST first — the driver validates the mode without touching anything, and
   a mode that fails the test is never written.
2. A revert timer — the write goes through, and unless the user keeps it within
   `REVERT_TIMEOUT_S` the prior mode is written back: Windows' own "keep these
   display settings?" pattern. A change whose prior mode could not be read is
   refused outright, since a write that cannot be undone is a one-way door.

Only the part that is wrong is written. Fixing a refresh rate never raises a
resolution the user lowered on purpose, and the other way round.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fpstune.settings.base import Reading

if TYPE_CHECKING:
    from fpstune.utils.detect import MonitorInfo

logger = logging.getLogger(__name__)

REVERT_TIMEOUT_S = 15.0

DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000

NATIVE = "native"
NOT_NATIVE = "not_native"
NOT_AVAILABLE = "not_available"

_pending_lock = threading.Lock()
_pending_reverts: dict[str, dict[str, Any]] = {}


# --- identity ---------------------------------------------------------------


def monitor_key(monitor: MonitorInfo, monitors: list[MonitorInfo]) -> str:
    """A stable key for one monitor, for its setting id (C5).

    The EDID hardware id names the model, which two identical monitors share, so
    a second unit of the same model gets an ordinal in the order Windows lists
    them. The device name (`\\\\.\\DISPLAY1`) is never the key: Windows renumbers
    it when outputs change.
    """
    base = monitor.hardware_id or monitor.friendly_name or monitor.name
    twins = [m for m in monitors if (m.hardware_id or m.friendly_name or m.name) == base]
    ordinal = twins.index(monitor) if monitor in twins else 0
    digest = hashlib.sha1(f"{base}|{ordinal}".encode()).hexdigest()[:10]
    return f"mon{digest}"


def find_monitor(key: str) -> MonitorInfo | None:
    """The connected monitor with this key, read fresh."""
    from fpstune.utils.hardware_manager import hardware_manager

    monitors = hardware_manager.detect_monitors()
    return next((m for m in monitors if monitor_key(m, monitors) == key), None)


def device_name(monitor: MonitorInfo) -> str:
    return monitor.name if monitor.name.startswith("\\\\.\\") else f"\\\\.\\{monitor.name}"


# --- the plan ---------------------------------------------------------------


@dataclass(frozen=True)
class ModePlan:
    """What would be written to put this monitor at its own best mode."""

    width: int
    height: int
    refresh: int
    fields: int

    @property
    def needed(self) -> bool:
        return self.fields != 0


def target_refresh(monitor: MonitorInfo) -> int:
    """The panel's own ceiling: the mode-list maximum, the EDID's preferred rate only
    as a fallback — a high-refresh panel's EDID often *prefers* 60 Hz."""
    return monitor.max_refresh_rate_hz or monitor.native_refresh_rate_hz


def plan_for(monitor: MonitorInfo) -> ModePlan:
    fields = 0
    if not monitor.is_resolution_optimal:
        fields |= DM_PELSWIDTH | DM_PELSHEIGHT
    if not monitor.is_refresh_optimal:
        fields |= DM_DISPLAYFREQUENCY
    return ModePlan(monitor.native_width, monitor.native_height, target_refresh(monitor), fields)


def is_readable(monitor: MonitorInfo) -> bool:
    """Native mode and ceiling are both known: anything less is not judged."""
    return bool(
        monitor.is_active
        and monitor.native_width
        and monitor.native_height
        and target_refresh(monitor)
    )


# --- the guarded write ------------------------------------------------------


def run_mode_change(
    device: str, width: int, height: int, refresh: int, fields: int
) -> tuple[str, tuple[int, int, int] | None]:
    """Test, then write, one display mode; return (status, prior mode or None).

    Status is NOPRIOR, TESTFAIL:<code>, SUCCESS or ERROR:<code>.
    """
    from fpstune.utils.winapi import display as winapi_display
    from fpstune.utils.winapi.display import DISP_CHANGE_SUCCESSFUL

    prior_mode = winapi_display.current_mode(device)
    if (
        prior_mode is None
        or prior_mode.width <= 0
        or prior_mode.height <= 0
        or prior_mode.refresh_hz <= 0
    ):
        return "NOPRIOR", None
    prior = (prior_mode.width, prior_mode.height, prior_mode.refresh_hz)

    test = winapi_display.change_mode(device, width, height, refresh, fields, test_only=True)
    if test != DISP_CHANGE_SUCCESSFUL:
        return f"TESTFAIL:{test}", prior
    result = winapi_display.change_mode(device, width, height, refresh, fields, test_only=False)
    return ("SUCCESS" if result == DISP_CHANGE_SUCCESSFUL else f"ERROR:{result}"), prior


def schedule_revert(
    device: str, prior: tuple[int, int, int], fields: int, setting_id: str | None = None
) -> None:
    """Write the prior mode back after the timeout unless the change is kept."""
    from fpstune.utils.hardware_manager import hardware_manager

    def _revert() -> None:
        with _pending_lock:
            _pending_reverts.pop(device, None)
        width, height, refresh = prior
        try:
            status, _ = run_mode_change(device, width, height, refresh, fields)
            from fpstune.utils.logger import log_activity

            log_activity(
                f"Display {device} not kept — put back to {width}x{height} @ {refresh} Hz",
                "warning",
            )
            if setting_id is not None and status == "SUCCESS":
                # The change history must not claim a mode the machine no longer has.
                from fpstune.safety.history import get_change_journal

                get_change_journal().record(setting_id, "revert", NOT_NATIVE)
            hardware_manager.invalidate_cache("monitors")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Display revert failed for %s: %s", device, exc)

    with _pending_lock:
        stale = _pending_reverts.pop(device, None)
        if stale is not None:
            stale["timer"].cancel()
        timer = threading.Timer(REVERT_TIMEOUT_S, _revert)
        timer.daemon = True
        _pending_reverts[device] = {
            "timer": timer,
            "prior": prior,
            "reverts_at": time.monotonic() + REVERT_TIMEOUT_S,
        }
        timer.start()


def cancel_revert(device: str) -> bool:
    """Keep the applied mode: cancel its pending revert. False when none exists."""
    with _pending_lock:
        pending = _pending_reverts.pop(device, None)
    if pending is None:
        return False
    pending["timer"].cancel()
    return True


def pending_devices() -> list[str]:
    """Displays whose new mode is waiting to be kept."""
    with _pending_lock:
        return list(_pending_reverts)


def seconds_until_revert() -> float:
    """How long until the first pending display goes back; 0 when none is pending."""
    with _pending_lock:
        deadlines = [p["reverts_at"] for p in _pending_reverts.values()]
    return max(0.0, min(deadlines) - time.monotonic()) if deadlines else 0.0


def keep_all() -> list[str]:
    """Keep every mode waiting for confirmation; return the devices kept."""
    kept = [device for device in pending_devices() if cancel_revert(device)]
    return kept


@dataclass(frozen=True)
class WriteOutcome:
    """How a guarded mode write ended: `written`, `unchanged`, `noprior`,
    `testfail` or `error`, with the sentence a user reads."""

    kind: str
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.kind in ("written", "unchanged")


def write_native(monitor: MonitorInfo, setting_id: str | None = None) -> WriteOutcome:
    """Put `monitor` at its own best mode, guarded; the one write path, shared by
    the Hardware-panel button and the per-monitor setting."""
    from fpstune.utils.hardware_manager import hardware_manager

    plan = plan_for(monitor)
    if not plan.needed:
        return WriteOutcome("unchanged")
    device = device_name(monitor)
    status, prior = run_mode_change(device, plan.width, plan.height, plan.refresh, plan.fields)
    if status == "NOPRIOR":
        return WriteOutcome(
            "noprior",
            "The display's current mode could not be read, so the change was refused — "
            "a mode that could not be reverted would be a one-way door.",
        )
    if status.startswith("TESTFAIL:"):
        code = status.split(":", 1)[1]
        return WriteOutcome(
            "testfail",
            f"The driver rejected {plan.width}x{plan.height} @ {plan.refresh} Hz before "
            f"anything was written (CDS_TEST returned {code}). Nothing was changed.",
        )
    if status != "SUCCESS" or prior is None:
        code = status.removeprefix("ERROR:") or "no output"
        return WriteOutcome("error", f"Failed to change display settings (code: {code})")
    schedule_revert(device, prior, plan.fields, setting_id)
    hardware_manager.invalidate_cache("monitors")
    return WriteOutcome("written")


# --- the setting's detect and apply ----------------------------------------


def mode_reading(monitor: MonitorInfo) -> Reading:
    """`native` or `not_native`, with the numbers the row explains it with."""
    value = NATIVE if not plan_for(monitor).needed else NOT_NATIVE
    return Reading(
        value,
        {
            "kind": "display_mode",
            "width": monitor.width,
            "height": monitor.height,
            "refresh_hz": monitor.refresh_rate_hz,
            "native_width": monitor.native_width,
            "native_height": monitor.native_height,
            "max_refresh_hz": target_refresh(monitor),
            "primary": monitor.is_primary,
            "supports_vrr": monitor.supports_vrr,
        },
    )


def display_mode_status(args: dict[str, Any]) -> str | Reading:
    """PYTHON_DETECTORS entry: this monitor's mode against its own best."""
    if sys.platform != "win32":
        return NOT_AVAILABLE
    # The cached monitor list (C7); `write_native` drops it after every write,
    # so the verify that follows an apply reads the mode it just set.
    monitor = find_monitor(str(args.get("monitor", "")))
    if monitor is None or not is_readable(monitor):
        return NOT_AVAILABLE
    return mode_reading(monitor)


def display_mode_native(args: dict[str, Any]) -> tuple[bool, str | None]:
    """PYTHON_ACTIONS entry: write the native mode, guarded by the revert timer."""
    if sys.platform != "win32":
        return False, "Not available on this platform"
    if args.get("value") != NATIVE:
        return False, "Only the monitor's own native mode can be written"
    monitor = find_monitor(str(args.get("monitor", "")))
    if monitor is None:
        return False, "This monitor is no longer connected"
    if not is_readable(monitor):
        return False, "This monitor's native mode could not be read"
    outcome = write_native(monitor, str(args.get("setting_id") or "") or None)
    return outcome.ok, (outcome.message or None)
