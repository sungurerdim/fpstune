"""Apply actions that run in Python rather than as PowerShell text.

``ACTION_COMMANDS`` maps an ``apply_command`` key to a PowerShell script. Some
actions have no business in PowerShell: the standby-list purge needs a native
kernel call, and reaching ``ntdll`` from a script means compiling a C# class
with ``Add-Type`` — the pattern Windows Defender flags as trojan behaviour
(2026-09-02). Those actions live here as plain functions with the same contract
the executor already speaks, ``(ok, message)``, and the executor consults this
table before it ever builds a command line.

An action's message is what the user reads after apply, so it states what was
measured on this machine and never a figure from somewhere else (C11).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fpstune.settings.applicability import NOT_AVAILABLE
from fpstune.utils.winapi.memory import purge_standby_list

PythonAction = Callable[[dict[str, Any]], tuple[bool, str | None]]
PythonDetector = Callable[[dict[str, Any]], str]


def purge_standby(_args: dict[str, Any]) -> tuple[bool, str | None]:
    """Drop the standby list and report the megabytes it actually released."""
    outcome = purge_standby_list()
    if not outcome.ok:
        return False, (
            f"The kernel refused the standby-list purge (NTSTATUS {outcome.status:#010x}); "
            "it needs an elevated process holding SeProfileSingleProcessPrivilege"
        )
    if outcome.before is None or outcome.after is None:
        return True, "Standby list purged; the page counts could not be read to size it"
    return True, (
        f"Standby list purged: {outcome.released_mb} MB released "
        f"(standby {outcome.before.standby_mb} MB before, {outcome.after.standby_mb} MB after)"
    )


PYTHON_ACTIONS: dict[str, PythonAction] = {
    "purge_standby": purge_standby,
}


# Windows reports Wi-Fi signal quality on a 0–100 scale that maps linearly onto
# -100..-50 dBm (WLAN_ASSOCIATION_ATTRIBUTES.wlanSignalQuality). 60 is about
# -70 dBm: below it, rate adaptation drops the PHY rate and retries climb, which
# a player feels as latency spikes before any throughput figure moves.
WEAK_SIGNAL_PERCENT = 60

# The 2.4 GHz band, by the connected BSS's centre frequency in kHz.
_BAND_2_4_GHZ = (2_400_000, 2_500_000)


def classify_wifi_link(signal_percent: int, center_khz: int) -> str:
    """One word for the link: ``weak_signal``, ``on_2_4ghz`` or ``good``.

    Signal first: a weak 5 GHz link is the bigger problem and the nearer fix.
    A centre frequency of 0 means no BSS entry matched the connected BSSID, so
    the band is unknown and only the signal is judged.
    """
    if signal_percent < WEAK_SIGNAL_PERCENT:
        return "weak_signal"
    if _BAND_2_4_GHZ[0] <= center_khz < _BAND_2_4_GHZ[1]:
        return "on_2_4ghz"
    return "good"


def wifi_link_quality(args: dict[str, Any]) -> str:
    """The connected radio's link quality, or the absent sentinel when it is not connected."""
    from fpstune.utils.winapi import wlan

    guid = str(args.get("interface_guid", "")).lower().strip("{}")
    for record in wlan.query_connected():
        if record.interface_guid == guid:
            return classify_wifi_link(record.signal_percent, record.center_khz)
    return NOT_AVAILABLE


# Detect counterparts of PYTHON_ACTIONS: a reading taken through a native API
# (wlanapi here) rather than a script. The executor consults this table by the
# setting's ``detect_command`` key before it builds any command line.
PYTHON_DETECTORS: dict[str, PythonDetector] = {
    "wifi_link_quality": wifi_link_quality,
}
