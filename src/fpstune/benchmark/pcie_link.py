"""Whether the graphics card got the lanes it was built for.

A card negotiated at x8 in an x16 slot has had its ceiling lowered before any
setting was applied — a dirty slot, a riser, a second M.2 drive stealing lanes,
or a laptop that drops the link on battery. It costs frames on a card fast
enough to notice, and nothing in fpstune ever looked: `detect.py` reads the
card's identity and its memory, never its link.

This is an advisory reading in the sense C1 means it — the machine's own report
about its own ceiling — and the answer is derived rather than declared: the
lane count and the link generation come from the device's own PCI properties,
via `Get-PnpDeviceProperty`, keyed by the `PNPDeviceID` the GPU already reports
(C5).

**Not every adapter answers, and that is not a failure.** Measured here: the
discrete GPU reports `CurrentLinkWidth = 16`, `MaxLinkWidth = 16` and both link
speeds as `4`; the integrated one returns empty for all four, because an iGPU is
not on a PCIe link at all. So an adapter with no properties is skipped, and a
machine where *no* adapter answers says so rather than reporting a card at zero
lanes.

**The speed is an enumeration, not a rate.** Windows reports `4`, which is
16 GT/s — PCIe 4.0. The mapping is written out below rather than inferred, and
an enumeration this build does not know keeps its raw value in `detail` instead
of being turned into a number that would be wrong.
"""

from __future__ import annotations

import time
from typing import Any

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.benchmark.win_query import query_rows
from fpstune.utils.logger import get_logger

logger = get_logger()

_QUERY_SECONDS = 6.0

NO_LINK_DATA = (
    "no display adapter here reports a PCIe link width — an integrated GPU is "
    "not on a PCIe link, and a virtual adapter has none to report"
)

# What Windows' `CurrentLinkSpeed` enumeration means, in transfers per second.
# Written out because the enumeration is not the rate: `4` is PCIe 4.0 at
# 16 GT/s, and reading it as a number would report a fourth of the link.
LINK_SPEED_GTS: dict[int, float] = {
    1: 2.5,
    2: 5.0,
    3: 8.0,
    4: 16.0,
    5: 32.0,
    6: 64.0,
}

_PROPERTIES = (
    ("current_width", "DEVPKEY_PciDevice_CurrentLinkWidth"),
    ("max_width", "DEVPKEY_PciDevice_MaxLinkWidth"),
    ("current_speed", "DEVPKEY_PciDevice_CurrentLinkSpeed"),
    ("max_speed", "DEVPKEY_PciDevice_MaxLinkSpeed"),
)


def build_script() -> str:
    """Every display adapter's PCI link properties, as one expression.

    All four properties in one `Get-PnpDeviceProperty` call per adapter, which
    is the difference between 0.7 s and 7 s on this machine: the cmdlet's cost is
    per invocation, not per key. Wrapped so an adapter that has no PCI link — an
    integrated GPU — leaves the others alone rather than taking the query down.
    """
    keys = ",".join(f"'{key}'" for _, key in _PROPERTIES)
    fields = ";".join(f"{name}=$v['{key}']" for name, key in _PROPERTIES)
    return (
        "Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | ForEach-Object { "
        "$id=$_.PNPDeviceID; $adapter=[string]$_.Name; $v=@{}; "
        f"foreach($x in @(Get-PnpDeviceProperty -InstanceId $id -KeyName {keys} "
        "-ErrorAction SilentlyContinue)){ $v[[string]$x.KeyName]=$x.Data }; "
        "[pscustomobject]@{"
        "adapter=$adapter;"
        "instance_id=[string]$id;"
        f"{fields}"
        "} }"
    )


def _lanes(value: Any) -> int | None:
    """A lane count, or None when the device reported nothing.

    An empty string is what a device with no PCIe link returns, and it is not a
    link of zero lanes.
    """
    if value is None or value == "":
        return None
    try:
        lanes = int(float(value))
    except (TypeError, ValueError):
        return None
    return lanes if lanes > 0 else None


class PcieLinkBench:
    """The lanes and the generation the graphics card actually negotiated."""

    key = "pcie_link"
    label = "Graphics card link"
    requires = "a display adapter on a PCIe link, which an integrated GPU is not"

    def timeout_seconds(self, repeats: int) -> float:
        return deadline_for(_QUERY_SECONDS, repeats)

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def sample(self) -> tuple[list[dict[str, Any]], str]:
        """Every adapter that reports a link, or an empty list and the reason."""
        rows, reason = query_rows(build_script(), timeout=45, component="benchmark.pcie_link")
        if reason:
            return [], reason
        linked = [row for row in rows if _lanes(row.get("current_width")) is not None]
        if not linked:
            return [], NO_LINK_DATA
        return linked, ""

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        width: list[float] = []
        speed: list[float] = []
        adapters: list[dict[str, Any]] = []

        for _ in range(repeats):
            rows, reason = self.sample()
            if not rows:
                return BenchResult(
                    bench=self.key,
                    label=self.label,
                    ran=False,
                    reason=reason,
                    duration_seconds=time.perf_counter() - started,
                )

            adapters = [_describe(row) for row in rows]
            # The widest link on the machine is the graphics card that matters:
            # a capture card or a second adapter on x1 is not the one drawing
            # the game, and taking the narrowest would report its link as the
            # machine's ceiling.
            primary = max(adapters, key=lambda row: row["max_width"] or 0)
            if primary["current_width"]:
                width.append(float(primary["current_width"]))
            if primary["current_speed_gts"]:
                speed.append(float(primary["current_speed_gts"]))

        readings: dict[str, BenchReading] = {}
        if width:
            readings["pcie_link_width"] = BenchReading(
                "pcie_link_width", width, "lanes", higher_is_better=True
            )
        if speed:
            readings["pcie_link_speed_gts"] = BenchReading(
                "pcie_link_speed_gts", speed, "GT/s", higher_is_better=True
            )

        if not readings:
            return BenchResult(
                bench=self.key,
                label=self.label,
                ran=False,
                reason=NO_LINK_DATA,
                duration_seconds=time.perf_counter() - started,
            )

        primary = max(adapters, key=lambda row: row["max_width"] or 0)
        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings=readings,
            detail={
                "adapters": adapters,
                # The whole point of the reading, in the form a user reads it:
                # "x8 of x16" is a lowered ceiling, "x16 of x16" is not.
                "summary": _summary(primary),
                "at_full_width": primary["current_width"] == primary["max_width"],
                "at_full_speed": primary["current_speed_gts"] == primary["max_speed_gts"],
            },
            duration_seconds=time.perf_counter() - started,
        )


def _describe(row: dict[str, Any]) -> dict[str, Any]:
    """One adapter's link, with the enumerations translated where they are known."""
    current_speed = _lanes(row.get("current_speed"))
    max_speed = _lanes(row.get("max_speed"))
    described = {
        "adapter": str(row.get("adapter") or ""),
        # C5: the PnP instance id, which survives the card moving slot.
        "instance_id": str(row.get("instance_id") or ""),
        "current_width": _lanes(row.get("current_width")),
        "max_width": _lanes(row.get("max_width")),
        "current_speed_gts": LINK_SPEED_GTS.get(current_speed or 0),
        "max_speed_gts": LINK_SPEED_GTS.get(max_speed or 0),
    }
    if current_speed is not None and described["current_speed_gts"] is None:
        # An enumeration this build has not seen. Kept raw rather than turned
        # into a rate that would be invented.
        described["current_speed_enum"] = current_speed
    return described


def _summary(adapter: dict[str, Any]) -> str:
    """ "x8 of x16, 8 GT/s of 16 GT/s" — the sentence a user can act on."""
    parts = []
    if adapter["current_width"] and adapter["max_width"]:
        parts.append(f"x{adapter['current_width']} of x{adapter['max_width']}")
    if adapter["current_speed_gts"] and adapter["max_speed_gts"]:
        parts.append(f"{adapter['current_speed_gts']:g} GT/s of {adapter['max_speed_gts']:g} GT/s")
    return ", ".join(parts)
