"""Answer which documented cause of CoD's packet-burst warning applies here.

The warning is the reason this module exists. The IW engine cannot distinguish
"the packet arrived late" from "I processed it late", so a client-side CPU or
VRAM stall raises exactly the same three orange squares as real packet loss.
Players therefore replace routers and upgrade internet plans to fix a GPU that
ran out of VRAM. Sources:

- https://hone.gg/blog/stop-and-fix-packet-burst-in-warzone/
- https://www.dexerto.com/call-of-duty/how-to-fix-packet-burst-in-mw3-modern-warfare-3-issue-explained-2376825/

No new detection happens here. Every input is a setting fpstune already reads,
re-read through the causal question "could this be raising the warning?", and
each finding names the setting that resolves it so the answer is actionable
rather than merely informative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from fpstune.utils.logger import get_logger

logger = get_logger()

CheckStatus = Literal["ok", "at_risk", "unknown"]


@dataclass(frozen=True)
class PacketBurstCheck:
    """One documented cause, evaluated against this machine."""

    id: str
    title: str
    status: CheckStatus
    detail: str
    # Setting that resolves it. The point of the diagnostic is that a finding
    # comes with the button that fixes it; a finding with no remedy is a
    # complaint.
    remedy_setting_id: str | None = None


@dataclass(frozen=True)
class PacketBurstReport:
    checks: list[PacketBurstCheck] = field(default_factory=list)

    @property
    def at_risk(self) -> list[PacketBurstCheck]:
        return [c for c in self.checks if c.status == "at_risk"]

    @property
    def unknown(self) -> list[PacketBurstCheck]:
        return [c for c in self.checks if c.status == "unknown"]

    @property
    def summary(self) -> str:
        if self.at_risk:
            return f"{len(self.at_risk)} likely cause(s) present"
        if self.unknown:
            return f"No cause found; {len(self.unknown)} could not be read"
        return "No known cause present on this machine"


def _status_for(current: Any, wanted: Any) -> CheckStatus:
    """Compare a detected value against the value that clears the cause."""
    from fpstune.settings.applicability import is_absent_reading, values_equal

    # Absence is the single sentinel set, never a local re-spelling: this used
    # to list two of the four by hand, so "not_supported" and "not_found" were
    # compared against the wanted value and reported as a cause of the warning.
    # The empty string is not one of the sentinels and is kept separately — a
    # detector that answered with nothing has not said the feature is missing,
    # only that it could not read it, and both mean "unknown" here.
    if current is None or is_absent_reading(current):
        return "unknown"
    if isinstance(current, str) and not current.strip():
        return "unknown"

    return "ok" if values_equal(current, wanted) else "at_risk"


# Each entry: the cause, the setting that governs it, and what the setting has
# to read for the cause to be cleared. Ordered by how often the sources name it.
_CHECKS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "texture_streaming",
        "On-demand texture streaming",
        "game_config:mw3:texture_streaming",
        "minimal",
        "MW3 downloads textures over HTTP during the match, on the same line the match "
        "uses. This is the fix the sources name first.",
    ),
    (
        "streaming_quality",
        "Streaming quality",
        "game_config:mw3:world_streaming_quality",
        "Low",
        "Optimized pulls high-quality textures mid-match. Low (Minimal) downloads only "
        "what the match needs.",
    ),
    (
        "vram_headroom",
        "VRAM headroom",
        "game_config:mw3:vram_scale",
        "",  # filled from the setting's own derived recommendation
        "With no headroom the card swaps textures to system RAM, and the stall is "
        "reported as a network problem.",
    ),
    (
        "frame_cap",
        "CPU headroom (frame cap)",
        "game_config:mw3:fps_cap_ingame",
        "",  # derived from the monitor
        "An uncapped frame rate keeps the CPU saturated, leaving no time to process "
        "packets when they arrive.",
    ),
    (
        "pause_rendering",
        "Rendering pause on focus loss",
        "game_config:mw3:pause_rendering",
        "false",
        "Not a cause of the warning, but it freezes the window so a burst cannot be "
        "seen happening on a second monitor.",
    ),
)


def build_report(registry: Any, detected: dict[str, Any] | None = None) -> PacketBurstReport:
    """Evaluate every known cause against the current settings.

    Args:
        registry: A ``SettingsRegistry`` to resolve settings from.
        detected: Optional map of setting id -> already-detected value. Passing
            the values a scan has just produced keeps this free; omitting it
            makes the report fall back to each setting's own recommendation,
            which reports configuration intent rather than machine state.
    """
    checks: list[PacketBurstCheck] = []
    values = detected or {}

    for check_id, title, setting_id, wanted, detail in _CHECKS:
        setting = registry.get(setting_id)
        if setting is None:
            checks.append(
                PacketBurstCheck(
                    id=check_id,
                    title=title,
                    status="unknown",
                    detail=f"{detail} (setting not registered on this machine)",
                    remedy_setting_id=setting_id,
                )
            )
            continue

        # An empty `wanted` means the right value is derived per machine, so the
        # setting's own recommendation is the only correct target.
        target = wanted or setting.recommended_value
        current = values.get(setting_id)
        status = _status_for(current, target) if setting_id in values else "unknown"

        checks.append(
            PacketBurstCheck(
                id=check_id,
                title=title,
                status=status,
                detail=detail,
                remedy_setting_id=setting_id,
            )
        )

    return PacketBurstReport(checks=checks)
