"""What this machine actually reaches on a fixed scene, and what that permits.

The product promises "the ceiling that machine and that connection are capable
of". Raising image quality is only a tweak while the machine is *already* at its
frame-rate ceiling; below it, the same change lowers the ceiling and becomes the
thing consequence 3 forbids.

Two questions, answered separately because they have different consequences.

**How much of the target does this machine reach?** Expressed as bands rather
than one threshold, since a system at 95% needs a nudge and one at 19% needs
everything the config can give and must not be offered a sharper image on top.
The boundaries are ratios of the machine's own target, never frame rates, so
they mean the same on a 60 Hz laptop and a 500 Hz desktop.

**Which side was the frame waiting on?** GPU, CPU, or both. This does not change
whether quality is affordable, but it changes which tweak is worth anything: a
machine short on frames because *both* sides are saturated cannot be fixed by
graphics settings alone, and saying otherwise wastes the user's time.

Unmeasured is treated as "no room". A change that costs frames has to earn its
recommendation, and silence is not evidence.

**One band for the machine, not one per game** (owner's decision, 2026-09-11).
The reading used to come from a capture of whatever game happened to be running,
which made it per-game by construction and made it hostage to the user starting
a match. Two consequences settled it: a machine with no game open never got a
band at all, and two captures of two firefights are two different workloads, so
the same title could report two bands in an hour. `benchmark.gpu_scene` renders
the same scene, in the same order, at the panel's own resolution, on demand —
so the number describes the machine rather than the match, and one number is the
honest amount of information a fixed scene produces. Which *settings* a band may
move is still per game, and stays in `headroom_policy`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fpstune.utils.logger import get_logger

if TYPE_CHECKING:
    from fpstune.benchmark.suite import BenchResult

logger = get_logger()

# Beside originals.json — the same per-user state directory, and the same reason:
# it describes this machine and must not travel with the install.
HEADROOM_PATH = Path.home() / ".fpstune" / "headroom.json"

# A measurement older than this is not evidence any more. Drivers change, the
# panel is swapped, the user re-tunes; a recommendation built on a stale number
# is the same defect as one built on a guess, only harder to notice.
MAX_AGE_SECONDS = 14 * 24 * 60 * 60

# How many windows the on-demand run is cut into. `scheduler.BENCH_REPEATS` and
# `suite.DEFAULT_REPEATS`, for the same reason: two is the floor at which a noise
# floor exists at all, three is the floor at which one outlier cannot own the
# median.
MEASURE_SAMPLES = 3


# How much of the target the machine reaches, and what each band permits.
#
# Bands rather than one threshold, because "is there room for quality" and "how
# hard should this try" are different questions. A machine at 95% of its panel
# needs a nudge; one at 19% needs everything the config can give and must not be
# offered a sharper image on top.
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

# What one measurement attempt ended up doing. Named rather than collapsed into
# a bool because the reasons are the useful part: "install the scene" and "close
# the game first" are different instructions to the person who pressed the
# button (C11 rule 3).
MEASURED = "measured"
PANEL_UNKNOWN = "panel_unknown"
SCENE_UNAVAILABLE = "scene_unavailable"
MEASURE_FAILED = "measure_failed"
BUSY = "busy"


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


def panel_target_fps() -> int | None:
    """The frame rate this machine's display could actually show.

    ``None`` when the panel will not say. A target guessed at 60 would report a
    300 Hz machine as having met its ceiling at a fifth of it, and the whole
    point of the measurement is to stop exactly that mistake.
    """
    from fpstune.settings.panel import primary_refresh_hz

    max_hz = primary_refresh_hz()
    if max_hz is None:
        return None
    return frame_cap_for_refresh(max_hz)


@dataclass(frozen=True)
class PerformanceHeadroom:
    """What the scene measured, against what this display could show.

    ``target_fps`` comes from the panel, so it is the same number the in-game
    frame cap derives — the point being that the two cannot disagree about what
    "fast enough" means.

    ``bottleneck`` says which side the frame waited on, and it is a separate
    question from how far short the machine fell. Two systems can sit at half
    their target and want different things done about it: one whose GPU is
    saturated has graphics settings to give, while one where both sides are
    saturated does not — and telling that user to lower shadows wastes their
    time. It is ``unknown`` whenever the run did not establish it, which is the
    honest answer rather than a guess at the likelier side.
    """

    measured_fps: float | None = None
    fps_1_percent_low: float | None = None
    target_fps: int | None = None
    measured_at: float | None = None
    bottleneck: str = TIER_UNKNOWN
    # PresentMon's PresentMode for most frames of the run. A fact the panel
    # shows verbatim; nothing scores it.
    present_mode: str | None = None
    # The resolution the scene was rendered at, which is the panel's own (C9).
    # Kept because the band only means anything if the load was the panel's: a
    # number from a 1080p window compared against a 1440p panel's target would
    # be a different machine's answer.
    width: int | None = None
    height: int | None = None

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
        """Which band this machine falls in."""
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


def _load() -> dict[str, Any]:
    try:
        with open(HEADROOM_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("headroom file unreadable, treating as unmeasured: %s", exc)
        return {}


def read_headroom(now: float | None = None) -> PerformanceHeadroom:
    """What this machine last measured, or an unmeasured result.

    ``now`` is a parameter rather than a call to the clock so the staleness rule
    can be tested without waiting two weeks.

    A file written by an older build held one entry per game and no top-level
    ``measured_fps``, so it reads as unmeasured here and is overwritten by the
    next scene run. That is the conservative direction and needs no migration:
    the worst it costs is one measurement.
    """
    entry = _load()

    measured_at = entry.get("measured_at")
    is_stale = (
        now is not None
        and isinstance(measured_at, (int, float))
        and now - measured_at > MAX_AGE_SECONDS
    )
    if is_stale:
        logger.debug("the headroom reading is stale; treating this machine as unmeasured")
        return PerformanceHeadroom()

    def number(key: str) -> float | None:
        value = entry.get(key)
        return float(value) if isinstance(value, (int, float)) else None

    def whole(key: str) -> int | None:
        value = entry.get(key)
        return int(value) if isinstance(value, (int, float)) else None

    bottleneck = entry.get("bottleneck")
    return PerformanceHeadroom(
        measured_fps=number("measured_fps"),
        fps_1_percent_low=number("fps_1_percent_low"),
        target_fps=whole("target_fps"),
        measured_at=measured_at if isinstance(measured_at, (int, float)) else None,
        bottleneck=str(bottleneck) if bottleneck else TIER_UNKNOWN,
        present_mode=str(entry["present_mode"]) if entry.get("present_mode") else None,
        width=whole("width"),
        height=whole("height"),
    )


def record_headroom(
    *,
    measured_fps: float,
    target_fps: int,
    fps_1_percent_low: float | None = None,
    measured_at: float,
    bottleneck: str = TIER_UNKNOWN,
    present_mode: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> bool:
    """Store this machine's measurement. Returns whether it was written.

    The file is replaced rather than merged: there is one current answer and no
    archive, so anything an older shape left behind goes with the write.

    Failures are logged and swallowed: an unwritable state directory must leave
    the product recommending conservatively, not stop it working.
    """
    if measured_fps <= 0 or target_fps <= 0:
        logger.debug("refusing to record a non-positive measurement")
        return False

    data = {
        "measured_fps": round(float(measured_fps), 2),
        "fps_1_percent_low": (
            round(float(fps_1_percent_low), 2) if fps_1_percent_low is not None else None
        ),
        "target_fps": int(target_fps),
        "measured_at": measured_at,
        "bottleneck": bottleneck,
        "present_mode": present_mode or None,
        "width": int(width) if width else None,
        "height": int(height) if height else None,
    }

    try:
        HEADROOM_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp = HEADROOM_PATH.with_suffix(".json.tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        temp.replace(HEADROOM_PATH)
    except OSError as exc:
        logger.debug("could not record the headroom reading: %s", exc)
        return False

    logger.debug(
        "headroom recorded: %.1f fps against a %d fps target",
        measured_fps,
        target_fps,
    )
    return True


def record_scene_result(result: BenchResult, *, target_fps: int, measured_at: float) -> bool:
    """Turn one `gpu_scene` run into this machine's band. Returns whether it wrote.

    The median of the run's own windows, never a single window: `fps_avg` is a
    list of samples by construction (C11 rule 2) and one of them is a reading
    nothing could put a noise floor under.

    ``bottleneck`` is read from the result's own detail and is ``unknown`` when
    the bench did not establish it. PresentMon publishes a GPU/CPU split only
    for a run it could attribute, and naming a side the scene never measured
    would move settings on a guess — `headroom_policy` reads this to decide
    which frame-buying settings are worth promoting.
    """
    if not result.ran:
        return False

    reading = result.readings.get("fps_avg")
    if reading is None:
        return False

    low = result.readings.get("fps_1_percent_low")
    detail = result.detail or {}
    bottleneck = detail.get("bottleneck")
    return record_headroom(
        measured_fps=reading.median,
        fps_1_percent_low=low.median if low is not None else None,
        target_fps=target_fps,
        measured_at=measured_at,
        bottleneck=str(bottleneck) if bottleneck else TIER_UNKNOWN,
        present_mode=str(detail["present_mode"]) if detail.get("present_mode") else None,
        width=detail.get("width") if isinstance(detail.get("width"), int) else None,
        height=detail.get("height") if isinstance(detail.get("height"), int) else None,
    )


def explain_capture_failure(stderr: str) -> str:
    """Turn PresentMon's own refusal into something a user can act on.

    Its two common refusals are both specific and both fixable, and neither has
    anything to do with what was on the screen:

    * ``access denied ... requires administrative privileges`` — PresentMon opens
      an ETW trace session, which an unelevated process cannot do.
    * ``unrecognized option`` — fpstune passed a flag this PresentMon build does
      not have, which is a bug here rather than anything about the machine.

    Args:
        stderr: What PresentMon printed, or the failure text carrying it.

    Returns:
        A sentence for the user, or "" when it says nothing recognisable — in
        which case the caller's own reason is the better one and is kept.
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


@dataclass(frozen=True)
class MeasurementOutcome:
    """What one attempt did, and what this machine's current reading is after it.

    ``headroom`` is filled in on every outcome, including the failures. A panel
    that cannot answer "did it measure" must still be able to answer "what does
    it say", and returning nothing on a failed attempt would blank a result the
    user could still read a minute ago.
    """

    outcome: str
    detail: str
    headroom: PerformanceHeadroom | None = None

    @property
    def measured(self) -> bool:
        return self.outcome == MEASURED


def measure_now(
    *,
    now: float | None = None,
    samples: int = MEASURE_SAMPLES,
    allow_download: bool = False,
) -> MeasurementOutcome:
    """Run the scene and record what this machine reached. The UI's button.

    Every reason it could not run is named rather than collapsed into a single
    false: the caller is a person deciding what to do next, and "close the game
    first" and "the scene is not installed" are different instructions.

    ``allow_download`` stays False here. The engine is a 1.3 GB download and
    that is a decision a user makes once, on its own screen — not something a
    "measure now" press spends on their behalf.
    """
    now = time.time() if now is None else now
    current = read_headroom(now=now)

    target = panel_target_fps()
    if target is None:
        return MeasurementOutcome(
            outcome=PANEL_UNKNOWN,
            detail="This display will not report its refresh rate, so there is nothing to "
            "measure the frame rate against.",
            headroom=current,
        )

    from fpstune.benchmark.gpu_scene import GpuSceneBench
    from fpstune.benchmark.operation_lock import operation_lock

    bench = GpuSceneBench(allow_download=allow_download)
    available, why = bench.is_available()
    if not available:
        return MeasurementOutcome(outcome=SCENE_UNAVAILABLE, detail=why, headroom=current)

    # The same mutex an apply, a cleanup and a bench share. The scene renders at
    # full speed for the best part of a minute; overlapping it with a write to
    # the machine would measure something halfway between two states.
    with operation_lock() as taken:
        if not taken:
            return MeasurementOutcome(
                outcome=BUSY,
                detail="Another fpstune operation is running. The scene would measure a "
                "machine halfway between two states, so it waits.",
                headroom=current,
            )
        result = bench.run(samples)

    if not result.ran:
        reason = result.reason or ""
        return MeasurementOutcome(
            outcome=MEASURE_FAILED,
            detail=explain_capture_failure(reason) or reason or "The scene recorded nothing.",
            headroom=current,
        )

    if not record_scene_result(result, target_fps=target, measured_at=now):
        # The scene ran and the number exists; it could not be stored. Reported
        # as a failure because the recommendation engine reads the file and not
        # this return, so "measured" would be true on screen and false in effect.
        return MeasurementOutcome(
            outcome=MEASURE_FAILED,
            detail="The scene ran, but its result could not be written to "
            f"{HEADROOM_PATH.name}, so nothing here has changed.",
            headroom=current,
        )

    after = read_headroom(now=now)
    return MeasurementOutcome(
        outcome=MEASURED,
        detail=f"This machine measured against the panel's {target} fps target",
        headroom=after,
    )
