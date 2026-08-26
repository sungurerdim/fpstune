"""What this machine actually achieves in a game, and what that permits.

The product promises "the ceiling that machine and that connection are capable
of". Raising image quality is only a tweak while the machine is *already* at its
frame-rate ceiling; below it, the same change lowers the ceiling and becomes the
thing consequence 3 forbids.

Measured on the machine this was written for: MW4 at 17 ms GPU time and 12.5 ms
CPU time — 59 fps against a 300 Hz panel. The quality raises that shipped in the
first pass would have cost roughly half of that, on a system already using a
fifth of its display. Nothing in the product knew that, because nothing in the
product was asking.

Two questions, answered separately because they have different consequences.

**How much of the target does this machine reach?** Expressed as bands rather
than one threshold, since a system at 95% needs a nudge and one at 19% — the
measured MW4 case — needs everything the config can give and must not be offered
a sharper image on top. The boundaries are ratios of the machine's own target,
never frame rates, so they mean the same on a 60 Hz laptop and a 500 Hz desktop.

**Which side was the frame waiting on?** GPU, CPU, or both. This does not change
whether quality is affordable, but it changes which tweak is worth anything: a
machine short on frames because *both* sides are saturated cannot be fixed by
graphics settings alone, and saying otherwise wastes the user's time.

Unmeasured is treated as "no room". A change that costs frames has to earn its
recommendation, and silence is not evidence.

Per game, because a machine that holds 300 fps in one title holds 60 in another,
and a recommendation built from the wrong game's numbers is worse than none.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fpstune.utils.logger import get_logger

logger = get_logger()

# Beside originals.json — the same per-user state directory, and the same reason:
# it describes this machine and must not travel with the install.
HEADROOM_PATH = Path.home() / ".fpstune" / "headroom.json"

# A measurement older than this is not evidence any more. Drivers change, the
# game patches, the user re-tunes; a recommendation built on a stale number is
# the same defect as one built on a guess, only harder to notice.
MAX_AGE_SECONDS = 14 * 24 * 60 * 60


# How much of the target the machine reaches, and what each band permits.
#
# Bands rather than one threshold, because "is there room for quality" and "how
# hard should this try" are different questions. A machine at 95% of its panel
# needs a nudge; one at 19% — the measured MW4 case — needs everything the
# config can give and must not be offered a sharper image on top.
#
# The boundaries are ratios of the machine's own target, never frame rates, so
# they mean the same thing on a 60 Hz laptop and a 500 Hz desktop. That is the
# whole reason they are expressed this way.
TIER_MET = "met"  # at or above target: frames are going unused
TIER_NEAR = "near"  # close enough that small savings finish the job
TIER_SHORT = "short"  # meaningfully under: spend the decoration
TIER_CRITICAL = "critical"  # less than half: spend everything that is not information
TIER_UNKNOWN = "unknown"  # no measurement, and silence is not evidence

_TIER_FLOORS: tuple[tuple[float, str], ...] = (
    (1.0, TIER_MET),
    (0.85, TIER_NEAR),
    (0.5, TIER_SHORT),
)

# The lowest a cap is allowed to land. A panel that reports a nonsense refresh
# must not produce a cap that costs the user frames they could have had.
MIN_FRAME_CAP = 30

# How far below the panel a frame cap sits, in Hz.
VRR_HEADROOM_HZ = 3


def frame_cap_for_refresh(max_hz: int) -> int:
    """The frame rate a panel of this refresh should be held at.

    Blur Busters' G-SYNC 101 measurements settle on refresh minus three: below
    the panel's own ceiling the frame rate stays inside the VRR window, where
    the display governs presentation and V-Sync never engages. Above it, V-Sync
    takes over and the latency the whole configuration was chosen to avoid
    arrives anyway.

    One function rather than the expression written out at each site, because
    the driver cap, the in-game caps and the measurement target all have to
    agree about what "fast enough" means on this panel. When they disagree the
    lowest one silently wins and every other setting looks broken.
    """
    return max(max_hz - VRR_HEADROOM_HZ, MIN_FRAME_CAP)


@dataclass(frozen=True)
class PerformanceHeadroom:
    """What a game measured, against what its display could show.

    ``target_fps`` comes from the panel, so it is the same number the in-game
    frame cap derives — the point being that the two cannot disagree about what
    "fast enough" means.

    ``bottleneck`` says which side the frame waited on, and it is a separate
    question from how far short the machine fell. Two systems can sit at half
    their target and want different things done about it: one whose GPU is
    saturated has graphics settings to give, while one where both sides are
    saturated does not — and telling that user to lower shadows wastes their
    time.
    """

    game: str
    measured_fps: float | None = None
    fps_1_percent_low: float | None = None
    target_fps: int | None = None
    measured_at: float | None = None
    bottleneck: str = TIER_UNKNOWN
    cpu_busy_ms: float | None = None
    gpu_time_ms: float | None = None
    input_latency_ms: float | None = None

    @property
    def achievement(self) -> float | None:
        """Fraction of the target reached. None when unmeasured."""
        if not self.is_measured:
            return None
        assert self.measured_fps is not None and self.target_fps is not None
        if self.target_fps <= 0:
            return None
        return self.measured_fps / self.target_fps

    @property
    def tier(self) -> str:
        """Which band this machine falls in, for this game."""
        ratio = self.achievement
        if ratio is None:
            return TIER_UNKNOWN
        for floor, name in _TIER_FLOORS:
            if ratio >= floor:
                return name
        return TIER_CRITICAL

    @property
    def is_measured(self) -> bool:
        return self.measured_fps is not None and self.target_fps is not None

    @property
    def has_headroom(self) -> bool:
        """Is there frame rate available to spend on image quality?

        False when unmeasured. That is the whole conservative default: a change
        that costs frames has to earn its recommendation, and silence is not
        evidence.

        Only the top band counts. Compares the average rather than the 1% low:
        the low is the honest number for "does this feel smooth", but it is
        almost never at a high-refresh target, and using it here would mean
        quality raises are never offered on any machine — a different way of
        being wrong.
        """
        return self.tier == TIER_MET

    @property
    def shortfall_percent(self) -> int | None:
        """How far under target, for the copy. None when there is no shortfall."""
        if not self.is_measured or self.has_headroom:
            return None
        assert self.measured_fps is not None and self.target_fps is not None
        if self.target_fps <= 0:
            return None
        return round((1 - self.measured_fps / self.target_fps) * 100)


def _load_all() -> dict[str, Any]:
    try:
        with open(HEADROOM_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("headroom file unreadable, treating as unmeasured: %s", exc)
        return {}


def read_headroom(game: str, now: float | None = None) -> PerformanceHeadroom:
    """Return what this game last measured, or an unmeasured result.

    ``now`` is a parameter rather than a call to the clock so the staleness rule
    can be tested without waiting two weeks.
    """
    entry = _load_all().get(game)
    if not isinstance(entry, dict):
        return PerformanceHeadroom(game=game)

    measured_at = entry.get("measured_at")
    is_stale = (
        now is not None
        and isinstance(measured_at, (int, float))
        and now - measured_at > MAX_AGE_SECONDS
    )
    if is_stale:
        logger.debug("headroom for %s is stale; treating as unmeasured", game)
        return PerformanceHeadroom(game=game)

    def number(key: str) -> float | None:
        value = entry.get(key)
        return float(value) if isinstance(value, (int, float)) else None

    target = entry.get("target_fps")
    bottleneck = entry.get("bottleneck")
    return PerformanceHeadroom(
        game=game,
        measured_fps=number("measured_fps"),
        fps_1_percent_low=number("fps_1_percent_low"),
        target_fps=int(target) if isinstance(target, (int, float)) else None,
        measured_at=measured_at if isinstance(measured_at, (int, float)) else None,
        bottleneck=str(bottleneck) if bottleneck else TIER_UNKNOWN,
        cpu_busy_ms=number("cpu_busy_ms"),
        gpu_time_ms=number("gpu_time_ms"),
        input_latency_ms=number("input_latency_ms"),
    )


def record_headroom(
    game: str,
    *,
    measured_fps: float,
    target_fps: int,
    fps_1_percent_low: float | None = None,
    measured_at: float,
    bottleneck: str = TIER_UNKNOWN,
    cpu_busy_ms: float | None = None,
    gpu_time_ms: float | None = None,
    input_latency_ms: float | None = None,
) -> bool:
    """Store one game's measurement. Returns whether it was written.

    Failures are logged and swallowed: an unwritable state directory must leave
    the product recommending conservatively, not stop it working.
    """
    if measured_fps <= 0 or target_fps <= 0:
        logger.debug("refusing to record a non-positive measurement for %s", game)
        return False

    data = _load_all()
    data[game] = {
        "measured_fps": round(float(measured_fps), 2),
        "fps_1_percent_low": (
            round(float(fps_1_percent_low), 2) if fps_1_percent_low is not None else None
        ),
        "target_fps": int(target_fps),
        "measured_at": measured_at,
        "bottleneck": bottleneck,
        "cpu_busy_ms": round(float(cpu_busy_ms), 3) if cpu_busy_ms else None,
        "gpu_time_ms": round(float(gpu_time_ms), 3) if gpu_time_ms else None,
        "input_latency_ms": round(float(input_latency_ms), 3) if input_latency_ms else None,
    }

    try:
        HEADROOM_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp = HEADROOM_PATH.with_suffix(".json.tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        temp.replace(HEADROOM_PATH)
    except OSError as exc:
        logger.debug("could not record headroom for %s: %s", game, exc)
        return False

    logger.debug(
        "headroom recorded for %s: %.1f fps against a %d fps target",
        game,
        measured_fps,
        target_fps,
    )
    return True


def explain_capture_failure(stderr: str) -> str:
    """Turn PresentMon's own refusal into something a user can act on.

    Its two common refusals are both specific and both fixable, and neither has
    anything to do with what the game was showing:

    * ``access denied ... requires administrative privileges`` — PresentMon opens
      an ETW trace session, which an unelevated process cannot do.
    * ``unrecognized option`` — fpstune passed a flag this PresentMon build does
      not have, which is a bug here rather than anything about the machine.

    Args:
        stderr: What PresentMon printed. Empty when it printed nothing.

    Returns:
        A sentence for the user, or "" when stderr says nothing recognisable.
    """
    lowered = stderr.lower()
    if "access denied" in lowered or "administrative privileges" in lowered:
        return (
            "PresentMon could not start a trace session because fpstune is not running "
            "as administrator. Restart fpstune elevated, or add this account to the "
            '"Performance Log Users" group.'
        )
    if "unrecognized option" in lowered:
        return (
            "PresentMon rejected one of the options fpstune passed it, so nothing was "
            "recorded. This is a version mismatch in fpstune, not a problem with the game."
        )
    return ""


def probe_running_game(
    game: str,
    target_fps: int,
    *,
    duration_seconds: int = 60,
    now: float,
) -> tuple[bool, str]:
    """Measure a game that is running right now, and record the result.

    Only runs when PresentMon is **already installed**. Downloading 15 MB behind
    a user who asked for a settings scan is not something to do quietly, and the
    conservative path costs them nothing but an opt-in they already had.

    Deliberately paired with the running-game check that blocks config writes:
    while the game is open fpstune cannot write to it anyway, so that window is
    exactly when there is nothing else to do and everything to measure.

    Returns:
        ``(recorded, reason)``. The reason is empty on success and on a genuinely
        empty capture; where PresentMon refused, it is PresentMon's own cause
        translated. It returns a reason rather than only a bool because the
        caller's fallback sentence — "it may have been in a menu" — was being
        printed over an access-denied error, which is a wrong diagnosis rather
        than a vague one.
    """
    from fpstune.settings.executors.game_processes import GAME_PROCESSES

    processes = GAME_PROCESSES.get(game)
    if not processes:
        return False, ""

    try:
        from fpstune.benchmark.presentmon import PresentMonBenchmark
    except Exception as exc:  # pragma: no cover - import guarded for packaging
        logger.debug("PresentMon unavailable, skipping headroom probe: %s", exc)
        return False, ""

    capture = PresentMonBenchmark()
    if not capture.is_installed():
        logger.debug("PresentMon not installed; %s stays unmeasured", game)
        return False, ""

    # GAME_PROCESSES stores names without the suffix, because that is how the
    # process snapshot reports them; PresentMon matches on the image name.
    process_name = f"{processes[0]}.exe"
    try:
        if not capture.start_capture(
            process_name=process_name,
            output_name=f"headroom_{game}",
            duration_seconds=duration_seconds,
        ):
            return False, ""
        # Let the timed capture run. `start_capture` only spawns PresentMon, so
        # calling `stop_capture` straight after it terminates the process before
        # it has recorded anything — measured against a running game on
        # 2026-08-25, a ten-second probe returned in 0.6 s with zero frames and
        # blamed the menu. The margin is for PresentMon's own startup.
        capture.wait_for_capture(duration_seconds + 10)
        capture_file = capture.stop_capture()
        stats = capture.analyze_capture(capture_file) if capture_file else None
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("headroom probe for %s failed: %s", game, exc)
        return False, ""

    reason = explain_capture_failure(capture.last_error)

    if stats is None or stats.fps_avg <= 0:
        logger.debug(
            "headroom probe for %s produced no frames%s",
            game,
            f": {reason}" if reason else "",
        )
        return False, reason

    return record_headroom(
        game,
        measured_fps=stats.fps_avg,
        fps_1_percent_low=stats.fps_1_percent_low or None,
        target_fps=target_fps,
        measured_at=now,
        bottleneck=stats.bottleneck,
        cpu_busy_ms=stats.cpu_busy_ms or None,
        gpu_time_ms=stats.gpu_time_ms or None,
        input_latency_ms=stats.input_latency_ms or None,
    ), reason
