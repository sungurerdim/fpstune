"""Which panel the game renders to, and the highest rate it can show.

Five call sites derived this independently — four discovery passes and the
headroom measurement — and the comment at the fourth one already admitted it
was a copy. The risk in a copy is not the duplication, it is that a frame cap
and the target it is measured against can drift apart: a driver cap built from
one reading of the panel and an in-game cap built from another are two answers
to one question.

The rate is always the panel's own maximum, never a constant. Zero means "the
panel did not say" and must stay zero: a 240 Hz display told it is 60 loses
three quarters of the frames it can show, so every caller treats an unknown as
"register nothing" rather than as a default.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fpstune.utils.detect import MonitorInfo

logger = logging.getLogger(__name__)


def primary_monitor(monitors: Sequence[MonitorInfo]) -> MonitorInfo | None:
    """Return the panel Windows calls primary, or the only one there is.

    Identified by the ``is_primary`` flag EnumDisplayDevices reports, never by
    model name or by position in the list (C5). Present-but-inactive panels are
    facts about the machine, not rendering targets — nothing derives from them.
    The fallback to the first active entry is for the case where no panel claims
    the flag at all — it is not an index-based identity, it is "there is only
    this".
    """
    active = [m for m in monitors if m.is_active]
    if not active:
        return None
    return next((m for m in active if m.is_primary), active[0])


def refresh_ceiling_hz(monitor: MonitorInfo) -> int:
    """The highest rate this panel reports, preferring the overclocked mode.

    ``max_refresh_rate_hz`` comes from EnumDisplaySettings and includes modes a
    panel reaches only when overclocked; ``native_refresh_rate_hz`` is what EDID
    declares. A panel that reports one and not the other is normal, so both are
    read before giving up.

    Returns:
        The rate in Hz, or 0 when the panel reports neither.
    """
    return int(monitor.max_refresh_rate_hz or monitor.native_refresh_rate_hz or 0)


def primary_refresh_hz() -> int | None:
    """Detect the panels and return the primary one's ceiling in Hz.

    Returns:
        The rate, or ``None`` when there is no panel, when detection failed, or
        when the panel reports no rate. All three mean the same thing to a
        caller — there is no number to derive from — and none of them may
        become 60.
    """
    from fpstune.utils.hardware_manager import hardware_manager

    try:
        monitors = hardware_manager.detect_monitors()
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("Panel refresh unknown, monitor detection failed: %s", exc)
        return None

    monitor = primary_monitor(monitors)
    if monitor is None:
        return None
    return refresh_ceiling_hz(monitor) or None
