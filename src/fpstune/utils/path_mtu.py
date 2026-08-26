"""Probe the path MTU of the internet route, by measurement rather than assumption.

The right MTU is whatever the line actually carries. On this dev machine 1500-byte
frames are rejected and 1492 pass, because the router terminates PPPoE and its
8-byte header eats the difference — a tool that "restored" 1500 would cause the
fragmentation it claims to fix. Equally, a tool that assumed 1492 would throw away
8 bytes of every frame on the majority of connections that really do carry 1500.
So fpstune measures, and when it cannot measure it says so and offers nothing.

Two implementation facts, both established on a real host rather than reasoned about:

* **The probe reads a status enum, never text.** ``ping.exe`` prints its verdict in
  the system language ("Paketin parçalanması gerekiyor" on this Turkish install), and
  its exit code cannot tell "too big" from "no answer" — both are 1. .NET's
  ``System.Net.NetworkInformation.Ping`` returns ``IPStatus``, whose members are
  ``Success`` / ``PacketTooBig`` / ``TimedOut`` in every locale. Measured here:
  payload 1472 -> PacketTooBig, 1464 -> Success. Same trap as the localised
  performance counters in ``_dpc_probe`` and the localised netsh output.
* **Only ``PacketTooBig`` proves a size is too large.** A ``TimedOut`` proves nothing
  — a dropped probe, a rate limiter, or a firewall that eats ICMP all look the same.
  Treating a timeout as "too big" is how a probe talks itself down to a floor value
  and quietly caps the line, so a timeout aborts the search instead.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# IPv4 header (20) + ICMP echo header (8). The probe sends payload; MTU adds these.
_IP_ICMP_OVERHEAD = 28

# Search bounds as payload sizes. The ceiling is standard Ethernet; the floor is the
# IPv6 minimum link MTU, below which a path is broken rather than merely small.
_MAX_PAYLOAD = 1500 - _IP_ICMP_OVERHEAD  # 1472
_MIN_PAYLOAD = 1280 - _IP_ICMP_OVERHEAD  # 1252

# Two well-known resolvers on different networks. If the first is unreachable or
# filtered, the second gives the probe a second opinion before it gives up.
_TARGETS = ("1.1.1.1", "8.8.8.8")

_PROBE_TIMEOUT_MS = 1200

# The result is stable for as long as the route is, and the scan must not pay for a
# fresh binary search per setting (C7: no subprocess per request for session-stable
# data). One probe per process; `reset_cache` exists for the tests.
_cache: dict[str, int | None] = {}


def _build_script(target: str) -> str:
    """Emit the whole binary search as one PowerShell script.

    It runs in a single process on purpose: the search is 8-9 probes, and paying a
    ~3.5 s PowerShell start for each one would cost more than every other detection
    in the scan put together.
    """
    return f"""
$ErrorActionPreference = 'Stop'
$ping = New-Object System.Net.NetworkInformation.Ping
$opt = New-Object System.Net.NetworkInformation.PingOptions(128, $true)

function Test-Payload([int]$size) {{
    $buf = New-Object byte[] $size
    # A lost probe reads exactly like a filtered one, so a non-answer is retried
    # once before it is believed.
    foreach ($attempt in 1..2) {{
        try {{
            $reply = $ping.Send('{target}', {_PROBE_TIMEOUT_MS}, $buf, $opt)
            $status = $reply.Status.ToString()
        }} catch {{
            $status = 'Error'
        }}
        if ($status -eq 'Success') {{ return 'ok' }}
        if ($status -eq 'PacketTooBig') {{ return 'toobig' }}
    }}
    return 'unknown'
}}

$hi = {_MAX_PAYLOAD}
$lo = {_MIN_PAYLOAD}

# The common case first: a full-size frame gets through, and there is nothing to fix.
$top = Test-Payload $hi
if ($top -eq 'ok') {{ Write-Output ('mtu=' + ($hi + {_IP_ICMP_OVERHEAD})); exit }}
if ($top -ne 'toobig') {{ Write-Output 'unknown'; exit }}

# If even the floor cannot get through, the path is filtered rather than small.
if ((Test-Payload $lo) -ne 'ok') {{ Write-Output 'unknown'; exit }}

# Invariant: $lo is confirmed to pass, $hi is confirmed to be too big.
while (($hi - $lo) -gt 1) {{
    $mid = [int](($lo + $hi) / 2)
    switch (Test-Payload $mid) {{
        'ok'     {{ $lo = $mid }}
        'toobig' {{ $hi = $mid }}
        default  {{ Write-Output 'unknown'; exit }}
    }}
}}

Write-Output ('mtu=' + ($lo + {_IP_ICMP_OVERHEAD}))
""".strip()


def _probe_target(target: str) -> int | None:
    """Run one binary search. Returns the path MTU, or None if it was inconclusive."""
    from fpstune.utils.powershell import run_powershell

    # 9 probes x 2 attempts x 1.2 s is the theoretical worst case; in practice a
    # PacketTooBig comes back from the first hop immediately.
    success, output = run_powershell(_build_script(target), timeout=40, component="path_mtu")
    if not success:
        logger.debug("Path MTU probe against %s failed: %s", target, output)
        return None

    line = output.strip().splitlines()[-1].strip() if output.strip() else ""
    if not line.startswith("mtu="):
        return None

    try:
        mtu = int(line[4:])
    except ValueError:
        return None

    # A value outside the bounds the script searched means the script did not do
    # what this function thinks it did — refuse it rather than ship it as a target.
    if not (_MIN_PAYLOAD + _IP_ICMP_OVERHEAD) <= mtu <= (_MAX_PAYLOAD + _IP_ICMP_OVERHEAD):
        logger.warning("Path MTU probe returned %d, outside the searched range", mtu)
        return None

    return mtu


def probe_path_mtu() -> int | None:
    """Return the largest MTU the internet path carries, or None if unmeasurable.

    None is a real answer and the common one on a filtered network: it means fpstune
    has no basis for a recommendation, and the MTU setting is not registered at all
    rather than registered with a guess.
    """
    if "value" in _cache:
        return _cache["value"]

    result: int | None = None
    for target in _TARGETS:
        result = _probe_target(target)
        if result is not None:
            logger.debug("Path MTU measured as %d via %s", result, target)
            break

    if result is None:
        logger.debug("Path MTU could not be measured against any target")

    _cache["value"] = result
    return result


def reset_cache() -> None:
    """Forget the measured value. For tests, and for a deliberate re-probe."""
    _cache.clear()
