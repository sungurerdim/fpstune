"""Keep one current measurement per game, and never a history.

``probe_running_game`` could always take a measurement; nothing ever called it,
so every recommendation that depends on one — the MW4 quality raises, and the
whole "is there room to spend frames" question — ran on a number a human had to
enter by hand. This is the part that calls it.

Three requirements, and the conflict between them is the reason this module
exists rather than a line in the startup path:

  1. **Measure without being asked.** The user should not have to know that a
     measurement is a thing that happens.
  2. **Measure again on demand**, from the UI, when the machine has changed.
  3. **The last result is always known**, and no archive is kept.

The conflict is in (1): a frame rate cannot be measured with nothing rendering,
and at startup the game is almost always closed. So "measure at startup" cannot
honestly mean "measure now" — it means *start watching*, and take the
measurement at the only moment it can be taken. A poll for a running game costs
one process snapshot, which is the same snapshot the config-write guard already
takes; the expensive part only happens when there is something to measure.

That pairing is not a coincidence. ``game_processes`` refuses to write a config
while the game is open, because the game flushes its own settings over the write
on exit. So the window where fpstune can write nothing is exactly the window
where it can measure everything.

**Once per game session.** A game that is seen running is measured once and then
left alone until it closes and opens again — a second capture of the same
unchanged session tells nobody anything, and a minute of PresentMon every
minute is a cost with no reading behind it. The user changing settings mid-
session is what the on-demand path is for.

Nothing here accumulates. ``headroom.json`` holds one entry per game and is
overwritten in place, which is what "the last result is always known" means:
not a log that has to be read backwards, one current answer per game.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from fpstune.settings.executors.game_processes import (
    GAME_LABELS,
    GAME_PROCESSES,
    game_is_running,
)
from fpstune.settings.panel import primary_refresh_hz
from fpstune.settings.performance_headroom import (
    PerformanceHeadroom,
    frame_cap_for_refresh,
    probe_running_game,
    read_headroom,
)
from fpstune.utils.logger import get_logger

logger = get_logger()

# How often to look for a game worth measuring. A process snapshot is cheap and
# a game does not open and close inside a minute, so anything faster buys
# nothing; anything much slower means a short session goes unmeasured.
POLL_INTERVAL_SECONDS = 60.0

# Let the startup work — registry warm-up, GPU detection, the first scan — have
# the machine to itself first. A measurement taken while the CPU is busy
# building the registry would describe fpstune, not the game.
FIRST_POLL_DELAY_SECONDS = 45.0

# Long enough to average out a firefight and a corridor.
#
# Ten seconds was chosen when the probe was invisible background work. It is too
# short to be one: a 1% low is by definition the worst 1% of frames, and over ten
# seconds at 60 fps that is six frames — a single stutter decides the number. A
# minute is what the benchmarking tools settle on for a repeatable pass, and it
# is the user's own request after watching the first one run.
CAPTURE_SECONDS = 60

# A recorded measurement younger than this is not worth retaking on its own.
# ``performance_headroom.MAX_AGE_SECONDS`` is a different rule for a different
# question: at two weeks a reading stops counting as evidence at all, while this
# is only "do not bother re-measuring yet".
REMEASURE_AFTER_SECONDS = 6 * 60 * 60

# What a measurement attempt ended up doing. The UI needs the distinction: "no
# game is running" is something the user can fix in a minute, and "PresentMon is
# not installed" is something they have to decide about.
MEASURED = "measured"
ALREADY_FRESH = "already_fresh"
NO_GAME_RUNNING = "no_game_running"
PRESENTMON_MISSING = "presentmon_missing"
PANEL_UNKNOWN = "panel_unknown"
PROBE_FAILED = "probe_failed"


@dataclass(frozen=True)
class MeasurementOutcome:
    """What one attempt did, and what the game's current reading is afterwards.

    ``headroom`` is filled in on every outcome, including the failures. A panel
    that cannot answer "did it measure" must still be able to answer "what does
    it say", and returning nothing on a failed attempt would blank a result the
    user could still read a minute ago.
    """

    game: str | None
    outcome: str
    detail: str
    headroom: PerformanceHeadroom | None = None

    @property
    def measured(self) -> bool:
        return self.outcome == MEASURED


def known_games() -> tuple[str, ...]:
    """Every game this machine could be measured on, in a stable order."""
    return tuple(sorted(GAME_PROCESSES))


def running_games() -> list[str]:
    """Which of the known games is holding its config in memory right now."""
    return [game for game in known_games() if game_is_running(game)]


def panel_target_fps() -> int | None:
    """The frame rate this machine's display could actually show.

    ``None`` when the panel will not say. A target guessed at 60 would report a
    300 Hz machine as having met its ceiling at a fifth of it, and the whole
    point of the measurement is to stop exactly that mistake.
    """
    max_hz = primary_refresh_hz()
    if max_hz is None:
        return None
    return frame_cap_for_refresh(max_hz)


def _presentmon_is_installed() -> bool:
    """Whether the capture tool is already here.

    Deliberately does not install it. Downloading 15 MB behind a user who opened
    a settings panel is not a decision to make on their behalf, and the honest
    failure — "not installed" — is one they can act on.
    """
    try:
        from fpstune.benchmark.presentmon import PresentMonBenchmark

        return bool(PresentMonBenchmark().is_installed())
    except Exception as exc:  # pragma: no cover - import guarded for packaging
        logger.debug("PresentMon unavailable: %s", exc)
        return False


def measure_game(
    game: str,
    *,
    now: float | None = None,
    duration_seconds: int = CAPTURE_SECONDS,
) -> MeasurementOutcome:
    """Take one measurement of a named game, right now.

    Every reason it could not be taken is named rather than collapsed into a
    single false: the caller is a person deciding what to do next, and "close
    something else" and "install PresentMon" are different instructions.
    """
    now = time.time() if now is None else now
    label = GAME_LABELS.get(game, game.upper())

    if game not in GAME_PROCESSES:
        return MeasurementOutcome(
            game=game,
            outcome=NO_GAME_RUNNING,
            detail=f"fpstune has no process name for {label}, so it cannot tell when it is running",
        )

    current = read_headroom(game, now=now)

    if not game_is_running(game):
        return MeasurementOutcome(
            game=game,
            outcome=NO_GAME_RUNNING,
            detail=f"{label} is not running. A frame rate needs something rendering to measure.",
            headroom=current,
        )

    target = panel_target_fps()
    if target is None:
        return MeasurementOutcome(
            game=game,
            outcome=PANEL_UNKNOWN,
            detail="This display will not report its refresh rate, so there is nothing to "
            "measure the frame rate against.",
            headroom=current,
        )

    if not _presentmon_is_installed():
        return MeasurementOutcome(
            game=game,
            outcome=PRESENTMON_MISSING,
            detail="PresentMon is not installed. Install it from the Benchmarks tab and "
            "fpstune can measure what this machine actually reaches.",
            headroom=current,
        )

    recorded, reason = probe_running_game(game, target, duration_seconds=duration_seconds, now=now)
    after = read_headroom(game, now=now)

    if not recorded:
        # PresentMon's own cause when it gave one. The fallback below is a
        # guess, and it was being printed over an access-denied error — which
        # made a fixable problem (run elevated) read as an unfixable one (you
        # were in a menu).
        return MeasurementOutcome(
            game=game,
            outcome=PROBE_FAILED,
            detail=reason
            or (
                f"The capture produced no frames for {label}. It may have been in a menu "
                "or minimised."
            ),
            headroom=after,
        )

    return MeasurementOutcome(
        game=game,
        outcome=MEASURED,
        detail=f"{label} measured against this panel's {target} fps target",
        headroom=after,
    )


def measure_now(game: str | None = None, *, now: float | None = None) -> MeasurementOutcome:
    """Measure on demand — the game named, or whichever one is running.

    ``game=None`` is what the UI's button sends: the user wants the number
    refreshed and should not have to tell fpstune which title they have open.
    """
    now = time.time() if now is None else now

    if game is not None:
        outcome = measure_game(game, now=now)
        if outcome.measured:
            _mark_attempted(game)
        return outcome

    candidates = running_games()
    if not candidates:
        return MeasurementOutcome(
            game=None,
            outcome=NO_GAME_RUNNING,
            detail="No game fpstune knows is running. Start one and measure again — a frame "
            "rate needs something rendering.",
        )

    result = measure_game(candidates[0], now=now)
    if result.measured:
        _mark_attempted(candidates[0])
    return result


def last_results(now: float | None = None) -> list[tuple[str, PerformanceHeadroom, bool]]:
    """Every known game's current reading, and whether it is running.

    Games without a measurement are included rather than filtered out. "Not
    measured yet" is an answer the user is entitled to see, and a list that
    silently omits them looks like a list of the games that exist.
    """
    return [(game, read_headroom(game, now=now), game_is_running(game)) for game in known_games()]


# Which games this process has already had a go at. Without it a probe that
# fails — no frames, PresentMon missing — would be retried every single poll for
# as long as the game stays open.
_lock = threading.Lock()
_attempted: set[str] = set()
_thread: threading.Thread | None = None
_stop = threading.Event()


def _mark_attempted(game: str) -> None:
    with _lock:
        _attempted.add(game)


def reset_watch_state() -> None:
    """Forget which games were attempted. For tests, and after a manual measure."""
    with _lock:
        _attempted.clear()


def poll_once(now: float | None = None) -> list[MeasurementOutcome]:
    """One pass: measure any running game that has not been tried this session.

    Separated from the thread so the decision — *should* this be measured — is
    testable without waiting a minute for a timer.
    """
    now = time.time() if now is None else now
    running = set(running_games())

    with _lock:
        # A game that has closed is eligible again: the next launch is a new
        # session, possibly after the user changed something, and that is worth
        # a fresh number.
        _attempted.intersection_update(running)
        pending = sorted(running - _attempted)
        _attempted.update(pending)

    outcomes: list[MeasurementOutcome] = []
    for game in pending:
        existing = read_headroom(game, now=now)
        if (
            existing.is_measured
            and existing.measured_at is not None
            and now - existing.measured_at < REMEASURE_AFTER_SECONDS
        ):
            outcomes.append(
                MeasurementOutcome(
                    game=game,
                    outcome=ALREADY_FRESH,
                    detail="A recent measurement already stands for this game",
                    headroom=existing,
                )
            )
            continue
        outcomes.append(measure_game(game, now=now))

    return outcomes


def _watch_loop() -> None:  # pragma: no cover - timing loop, poll_once is tested
    if _stop.wait(FIRST_POLL_DELAY_SECONDS):
        return
    while True:
        try:
            for outcome in poll_once():
                if outcome.measured:
                    logger.info("headroom: %s", outcome.detail)
                else:
                    logger.debug("headroom: %s (%s)", outcome.detail, outcome.outcome)
        except Exception as exc:
            # A background measurement failing must never take the API with it.
            logger.debug("headroom poll failed: %s", exc)
        if _stop.wait(POLL_INTERVAL_SECONDS):
            return


def start_headroom_watch() -> bool:
    """Begin watching for a game to measure. Returns whether a thread was started."""
    global _thread

    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        _thread = threading.Thread(target=_watch_loop, daemon=True, name="headroom-watch")
        _thread.start()
    return True


def stop_headroom_watch(timeout: float = 5.0) -> None:
    """Ask the watch thread to stop, and wait briefly for it."""
    global _thread

    _stop.set()
    thread = _thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
    _thread = None
