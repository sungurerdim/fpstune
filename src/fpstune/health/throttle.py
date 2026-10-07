"""Why was the machine slow: the part that was held back, named from what Windows measured.

The owner's case: a player got under half the machine's capacity in-game, suspected the
CPU was overheating, and could not confirm it. A temperature cannot confirm it — CPU
core temperature needs a kernel driver and is not read (`health.thermal`) — but the
*effect* of overheating can be measured without one: the processor is held below its own
nominal performance while it has work. That is what this reads, window by window, while
a game runs:

| Signal | Source | What it says |
|---|---|---|
| `% Performance Limit` | PDH, English counter path (`health.pdh`) | Windows reports the platform or power policy limiting the CPU below nominal |
| `% Processor Performance` | PDH | the performance actually delivered, as a share of nominal; above 100 % when it boosts |
| `% Passive Limit` per thermal zone | PDH | a zone is restricting the devices it controls: Windows' own passive *thermal* cooling |
| event 37, Kernel-Processor-Power | `benchmark.event_scan` | firmware held the processor below its speed, for how long; **not** why |
| active power plan's maximum processor state, battery | `health.power_state` | the power policy's own cap on the CPU |
| clock event reasons | `nvidia-smi` (`health.gpu_nvidia`) | why the GPU's clocks are below their ceiling |
| frame side | PresentMon's `FrameTimeStats.bottleneck` | which of CPU and GPU the frame waited on, when a capture exists |

**Verdicts, and what each one needs** (`attribute`):

- `cpu_thermal` — the CPU was limited *and* a thermal zone was passively throttling in
  the same window. Heat, by Windows' own definition of passive cooling.
- `cpu_power_limit` — the CPU was limited *and* the active power plan caps the processor
  below 100 %, or the machine is on battery. Both this and `cpu_thermal` can be true of
  one window; the first is the verdict and the other is listed in `also`.
- `gpu_thermal_or_power` — the driver reports a thermal slowdown, a hardware slowdown or
  a power brake for at least half the window. `sw_power_cap` is not one: it is the power
  governor at full load on every card.
- `none` — everything that can be read was read, and none of it shows a limit: the
  slowdown is not the CPU or GPU being held back.
- `unmeasured` — with the reason. This includes the case the issue names: the CPU *was*
  limited (the counter says so, or event 37 covers the window) and nothing readable says
  whether heat or power did it. Event 37 does not split them, and neither does
  `% Performance Limit`; that is reported as an unmeasured cause, never guessed.

**Frame side only breaks ties.** When both a CPU and a GPU limit are present, the side the
frame waited on goes first; with no capture, the CPU verdicts go first, and the rest are
listed in `also`.

**Event 37 is late evidence.** It is written once a cap has lasted a while, so a window
that ended a moment ago can be covered by an event that does not exist yet. The counters
are instant and are what a live window rests on; the event corroborates a window, and on a
later look it can show one the counters did not.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from fpstune.benchmark import event_scan
from fpstune.benchmark.event_scan import FirmwareLimit
from fpstune.benchmark.process_sampler import running_game
from fpstune.health import gpu_nvidia, pdh, power_state
from fpstune.health.model import Finding, Gap, Quantity, SourceResult
from fpstune.health.power_state import PowerState
from fpstune.utils.logger import get_logger
from fpstune.utils.system_tools import nvidia_smi

if TYPE_CHECKING:
    from fpstune.benchmark.presentmon import FrameTimeStats

logger = get_logger()

SOURCE = "throttle"

VerdictKind = Literal[
    "cpu_thermal", "cpu_power_limit", "gpu_thermal_or_power", "none", "unmeasured"
]

WINDOW_SECONDS = 6
"""How long one window samples while a game runs: long enough for several reads of a
once-a-second counter and of a driver tool that takes a second or two per call, short
enough that asking costs a poll's worth of time."""
SAMPLE_INTERVAL_SECONDS = 1.0
GPU_READS = 3
"""How many times the GPU's reasons are read in a window. Each is a driver-tool call of a
second or two, so three fill a window; a share of three readings is what `LIMIT_SHARE`
is applied to."""
GPU_JOIN_SECONDS = 10.0

NOMINAL_PERCENT = 100.0
LIMIT_TOLERANCE_PERCENT = 1.0
"""A limit counter below `NOMINAL - 1` is a limit. The counters are computed ratios and
report a fraction of a percent of arithmetic noise around an unlimited 100; a whole
percent is the smallest limit anyone sets."""

LIMIT_SHARE = 0.5
"""How much of a window a limit has to be present in to be the window's state: at least
half of the readings. One reading in six is a blip, not the window."""

LOADED_PROCESSORS = 1.0
"""How much CPU work, in logical processors' worth, counts as the CPU having work to limit.

A game keeps at least one thread saturated (the render or main thread), so below one
processor's worth of busy time there is nothing asking the CPU for more speed, and a
low performance reading there is the idle states doing their job, not a limit costing
frames. Expressed in processors rather than a percentage so it means the same on a
4-thread and a 24-thread CPU: one processor is 25 % of the first and 4 % of the second.
"""

PROBLEM_MEMORY_SECONDS = 30 * 60
"""How long a window's problem verdict stays a finding after it was observed.

Throttling at minute forty is something a player looks into after the match; a record
that ended with the game would be gone by then. Thirty minutes covers that, and a
verdict is dropped after it, so a fix is not contradicted forever by what it fixed.
"""

GPU_LIMIT_REASONS = frozenset(
    {"hw_thermal_slowdown", "sw_thermal_slowdown", "hw_slowdown", "hw_power_brake_slowdown"}
)
"""The clock event reasons that mean the GPU is held back by heat or by power it cannot draw."""

NO_GAME_YET = (
    "no game has been running while fpstune was watching, so in-game throttling has not "
    "been measured; it is read only while a known game is running"
)
COUNTERS_UNAVAILABLE = (
    "Windows' performance counters could not be read, so the CPU's own limits are not measured"
)
EVENTS_UNREADABLE = "the event log could not be read, so firmware limit events are not counted"
GPU_NO_REASONS = (
    "the NVIDIA driver reported no clock event reasons, so whether the GPU was held back "
    "cannot be told and the GPU cannot be ruled out"
)
GPU_VENDOR_GAP = (
    "the GPU's throttle reasons are readable only through an NVIDIA driver here; on this "
    "machine's graphics hardware they are not, so the GPU cannot be ruled out"
)


@dataclass(frozen=True)
class Sample:
    """One second of the CPU's own counters. Each is None when it was not readable."""

    busy_percent: float | None
    performance_percent: float | None
    performance_limit_percent: float | None
    passive_limit_percent: float | None
    """The lowest across the machine's thermal zones: any zone restricting counts."""


@dataclass(frozen=True)
class GpuSample:
    reasons: frozenset[str] | None
    """Every clock event reason active at that moment; None when the driver gave none."""


@dataclass(frozen=True)
class FrameSide:
    """The two numbers from a PresentMon capture that decide ties."""

    fps: float
    bottleneck: str
    """`cpu`, `gpu` or `unknown`, exactly as `FrameTimeStats.bottleneck` says."""


def frame_side(stats: FrameTimeStats) -> FrameSide:
    """The frame side of a PresentMon capture's statistics."""
    return FrameSide(fps=stats.fps_avg, bottleneck=stats.bottleneck)


@dataclass(frozen=True)
class Window:
    """Everything measured over one stretch of play."""

    started_at: float
    ended_at: float
    samples: tuple[Sample, ...] = ()
    gpu_samples: tuple[GpuSample, ...] = ()
    gpu_device_id: str | None = None
    gpu_reason: str = ""
    """Why `gpu_samples` is empty or unreadable, when it is."""
    firmware_limits: tuple[FirmwareLimit, ...] | None = None
    """Event 37 records near the window; None when the log could not be read."""
    power: PowerState = field(default_factory=lambda: PowerState(None, None))
    logical_processors: int | None = None
    frame: FrameSide | None = None


@dataclass(frozen=True)
class Verdict:
    """What the window was, why, and the numbers it rests on."""

    kind: VerdictKind
    reason: str
    also: tuple[VerdictKind, ...] = ()
    evidence: dict[str, float | str | bool | None] = field(default_factory=dict)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _share(flags: list[bool]) -> float:
    return sum(flags) / len(flags) if flags else 0.0


def _present(values: list[float | None]) -> list[float]:
    return [v for v in values if v is not None]


def attribute(window: Window) -> Verdict:
    """One verdict for the window, from the signals in it. See the module docstring."""
    evidence: dict[str, float | str | bool | None] = {}

    # ---- the CPU side -------------------------------------------------------
    limits = _present([s.performance_limit_percent for s in window.samples])
    busy = _present([s.busy_percent for s in window.samples])
    cpu_measured = bool(limits)
    busy_mean = _mean(busy)
    processors = window.logical_processors
    loaded: bool | None = None
    if busy_mean is not None and processors:
        loaded = busy_mean * processors / 100.0 >= LOADED_PROCESSORS
    limit_mean = _mean(limits)
    performance_mean = _mean(_present([s.performance_percent for s in window.samples]))
    evidence.update(
        cpu_busy_percent=busy_mean,
        cpu_performance_percent=performance_mean,
        cpu_performance_limit_percent=limit_mean,
        cpu_loaded=loaded,
    )

    floor = NOMINAL_PERCENT - LIMIT_TOLERANCE_PERCENT
    counter_limited = _share([v < floor for v in limits]) >= LIMIT_SHARE if limits else False
    overlapping = [
        e for e in (window.firmware_limits or ()) if e.overlaps(window.started_at, window.ended_at)
    ]
    evidence["firmware_limit_events"] = (
        len(overlapping) if window.firmware_limits is not None else None
    )
    cpu_limited = bool(loaded) and (counter_limited or bool(overlapping))

    passive = _present([s.passive_limit_percent for s in window.samples])
    thermal_zone = _share([v < floor for v in passive]) >= LIMIT_SHARE if passive else False
    evidence["thermal_zone_limiting"] = thermal_zone if passive else None

    cap = window.power.processor_cap_percent
    plan_caps = cap is not None and cap < NOMINAL_PERCENT
    on_battery = window.power.on_battery is True
    evidence.update(power_plan_cap_percent=cap, on_battery=window.power.on_battery)

    # ---- the GPU side -------------------------------------------------------
    readable = [s.reasons for s in window.gpu_samples if s.reasons is not None]
    gpu_measured = bool(readable)
    gpu_limited = (
        _share([bool(reasons & GPU_LIMIT_REASONS) for reasons in readable]) >= LIMIT_SHARE
        if readable
        else False
    )
    seen = sorted({r for reasons in readable for r in reasons & GPU_LIMIT_REASONS})
    evidence["gpu_limit_reasons"] = ",".join(seen) or None
    if window.frame is not None:
        evidence["frame_bottleneck"] = window.frame.bottleneck
        evidence["fps"] = window.frame.fps

    # ---- candidates, in the order they are preferred ------------------------
    cpu_candidates: list[VerdictKind] = []
    if cpu_limited and thermal_zone:
        cpu_candidates.append("cpu_thermal")
    if cpu_limited and (plan_caps or on_battery):
        cpu_candidates.append("cpu_power_limit")
    gpu_candidates: list[VerdictKind] = ["gpu_thermal_or_power"] if gpu_limited else []

    gpu_first = window.frame is not None and window.frame.bottleneck == "gpu"
    candidates = gpu_candidates + cpu_candidates if gpu_first else cpu_candidates + gpu_candidates

    if candidates:
        primary, *rest = candidates
        return Verdict(primary, _explain(primary, evidence, seen), tuple(rest), evidence)

    cause_unknown = cpu_limited and not thermal_zone and not plan_caps and not on_battery
    evidence["cpu_limited_cause_unknown"] = cause_unknown
    if cause_unknown:
        return Verdict("unmeasured", _unknown_cause(limit_mean, bool(overlapping)), (), evidence)

    missing = []
    if not cpu_measured:
        missing.append(COUNTERS_UNAVAILABLE)
    elif loaded is None:
        missing.append("how busy the CPU was could not be read, so a limit cannot be tied to work")
    if not gpu_measured:
        missing.append(
            window.gpu_reason or (GPU_NO_REASONS if window.gpu_samples else GPU_VENDOR_GAP)
        )
    if window.firmware_limits is None:
        # The event is late evidence and the counters are the live signal, so a log that
        # could not be read weakens a `none` without blocking it — and says so.
        evidence["firmware_events_unreadable"] = True
    if missing:
        return Verdict("unmeasured", "; ".join(missing), (), evidence)

    reason = "no limit was reported on the CPU or the GPU"
    if limit_mean is not None:
        reason += (
            f" (CPU performance limit {limit_mean:.0f} % of nominal; no GPU thermal, "
            "hardware-slowdown or power-brake reason): whatever held the frame rate down "
            "was not the processor or the graphics card being throttled"
        )
    if loaded is False:
        reason += "; the CPU was not busy enough for a limit to have cost frames"
    return Verdict("none", reason, (), evidence)


def _unknown_cause(limit_mean: float | None, firmware_events: bool) -> str:
    """The sentence for a CPU that was limited with nothing readable saying why."""
    held = "the CPU was held below its nominal performance while it had work"
    if limit_mean is not None:
        held += f" (Windows reports a limit of {limit_mean:.0f} % of nominal"
        held += ", and firmware limit events cover the window)" if firmware_events else ")"
    return (
        f"{held}, but nothing readable says whether heat or power did it: event 37 and the "
        "performance-limit counter do not separate them, no thermal zone was throttling, and "
        "the power plan and power source impose no cap — the cause is not guessed"
    )


def _explain(
    kind: VerdictKind, evidence: dict[str, float | str | bool | None], gpu: list[str]
) -> str:
    limit = evidence.get("cpu_performance_limit_percent")
    shown = f"{limit:.0f} %" if isinstance(limit, float) else "below nominal"
    if kind == "cpu_thermal":
        return (
            f"the CPU was held to {shown} of its nominal performance while a thermal zone was "
            "passively throttling the processors: heat, by Windows' own account"
        )
    if kind == "cpu_power_limit":
        cap = evidence.get("power_plan_cap_percent")
        why = (
            f"the active power plan caps the processor at {cap:.0f} %"
            if isinstance(cap, (int, float)) and cap < NOMINAL_PERCENT
            else "the machine is running on battery"
        )
        return f"the CPU was held to {shown} of its nominal performance and {why}: a power limit"
    return (
        "the GPU's driver reported its clocks held back by heat or by power it could not draw "
        f"({', '.join(gpu)}) for at least half the window"
    )


# ---- findings -----------------------------------------------------------------


def findings_from(verdict: Verdict, window: Window) -> list[Finding]:
    """A finding for each problem the verdict names, including the unknown-cause one."""
    limit = verdict.evidence.get("cpu_performance_limit_percent")
    cap = verdict.evidence.get("power_plan_cap_percent")
    nominal = Quantity(NOMINAL_PERCENT, "%")
    cpu_reading = Quantity(float(limit), "%") if isinstance(limit, float) else None

    findings = []
    for kind in (verdict.kind, *verdict.also):
        if kind == "cpu_thermal":
            findings.append(
                Finding(
                    "cpu",
                    None,
                    "warning",
                    "health.cpu.throttled_thermal",
                    cpu_reading,
                    nominal,
                    SOURCE,
                )
            )
        elif kind == "cpu_power_limit":
            reading = (
                Quantity(float(cap), "%")
                if isinstance(cap, (int, float)) and cap < NOMINAL_PERCENT
                else cpu_reading
            )
            findings.append(
                Finding(
                    "cpu", None, "warning", "health.cpu.throttled_power", reading, nominal, SOURCE
                )
            )
        elif kind == "gpu_thermal_or_power":
            findings.append(
                Finding(
                    "gpu",
                    window.gpu_device_id,
                    "warning",
                    "health.gpu.throttled",
                    None,
                    None,
                    SOURCE,
                )
            )
    if verdict.kind == "unmeasured" and verdict.evidence.get("cpu_limited_cause_unknown"):
        findings.append(
            Finding(
                "cpu",
                None,
                "warning",
                "health.cpu.throttled_unknown_cause",
                cpu_reading,
                nominal,
                SOURCE,
            )
        )
    return findings


# ---- sampling -----------------------------------------------------------------

_COUNTERS = {
    "performance": pdh.CPU_PERFORMANCE,
    "limit": pdh.CPU_PERFORMANCE_LIMIT,
    "busy": pdh.CPU_BUSY,
    "passive": pdh.ZONE_PASSIVE_LIMIT,
}


def _sample(row: dict[str, list[float]]) -> Sample:
    def one(name: str) -> float | None:
        values = row.get(name)
        return _mean(values) if values else None

    passive = row.get("passive")
    return Sample(
        busy_percent=one("busy"),
        performance_percent=one("performance"),
        performance_limit_percent=one("limit"),
        passive_limit_percent=min(passive) if passive else None,
    )


def _gpu_reasons() -> tuple[GpuSample | None, str | None, str]:
    """One read of the GPU's clock event reasons: the sample, its device id, or a reason."""
    if nvidia_smi() is None:
        # No NVIDIA driver is not "an NVIDIA card without its tool": this reader has
        # nothing to say about another vendor's GPU, and says that.
        return None, None, GPU_VENDOR_GAP
    gpus, reason = gpu_nvidia.gpus()
    if reason:
        return None, None, reason
    gpu = gpus[0]
    return GpuSample(gpu.active_reasons), gpu.device_id, ""


def sample_window(
    seconds: int = WINDOW_SECONDS,
    *,
    interval: float = SAMPLE_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    open_counters: Callable[[], pdh.CounterSet] | None = None,
    read_gpu: Callable[[], tuple[GpuSample | None, str | None, str]] = _gpu_reasons,
    read_events: Callable[[float], tuple[list[FirmwareLimit], str]] = event_scan.firmware_limits,
    read_power: Callable[[], PowerState] = power_state.read,
    logical_processors: int | None = None,
    frame: FrameSide | None = None,
) -> Window:
    """Watch the machine for `seconds`: counters each interval, the GPU's reasons beside them.

    The GPU tool takes a second or two per call, so it is read on its own thread beside
    the counters rather than between their reads: `GPU_READS` reads, one after another.
    """
    started = clock()
    counters: pdh.CounterSet | None = None
    try:
        counters = open_counters() if open_counters else pdh.CounterSet(_COUNTERS)
    except OSError as exc:
        logger.debug("Performance counters could not be opened: %s", exc)

    gpu_samples: list[GpuSample] = []
    gpu_device: list[str | None] = [None]
    gpu_reason = [""]

    def watch_gpu() -> None:
        for _ in range(GPU_READS):
            sample, device, reason = read_gpu()
            if sample is None:
                gpu_reason[0] = reason
                return
            gpu_samples.append(sample)
            gpu_device[0] = device

    watcher = threading.Thread(target=watch_gpu, name="throttle-gpu", daemon=True)
    watcher.start()

    samples: list[Sample] = []
    try:
        for _ in range(max(int(seconds / interval), 1)):
            sleep(interval)
            if counters is not None:
                samples.append(_sample(counters.read()))
    finally:
        if counters is not None:
            counters.close()
    watcher.join(timeout=GPU_JOIN_SECONDS)
    ended = clock()

    limits, events_reason = read_events(started)
    if events_reason:
        logger.debug("Firmware limit events unreadable: %s", events_reason)

    return Window(
        started_at=started,
        ended_at=ended,
        samples=tuple(samples),
        gpu_samples=tuple(gpu_samples),
        gpu_device_id=gpu_device[0],
        gpu_reason=gpu_reason[0],
        firmware_limits=None if events_reason else tuple(limits),
        power=read_power(),
        logical_processors=logical_processors or os.cpu_count(),
        frame=frame,
    )


# ---- what is remembered, and the source -----------------------------------------


@dataclass(frozen=True)
class Recorded:
    at: float
    game: str
    verdict: Verdict
    window: Window


_lock = threading.Lock()
_problems: dict[str, Recorded] = {}
_latest: Recorded | None = None


def reset() -> None:
    global _latest
    with _lock:
        _problems.clear()
        _latest = None


def record(game: str, window: Window, verdict: Verdict, *, at: float | None = None) -> Recorded:
    """Remember a window: always as the latest, and as a problem if it found one."""
    global _latest
    recorded = Recorded(time.time() if at is None else at, game, verdict, window)
    with _lock:
        _latest = recorded
        if findings_from(verdict, window):
            _problems[verdict.kind] = recorded
    return recorded


def remembered(now: float | None = None) -> tuple[Recorded | None, list[Recorded]]:
    """The latest window, and the problem windows still inside `PROBLEM_MEMORY_SECONDS`."""
    moment = time.time() if now is None else now
    with _lock:
        for kind in [k for k, r in _problems.items() if moment - r.at > PROBLEM_MEMORY_SECONDS]:
            del _problems[kind]
        return _latest, sorted(_problems.values(), key=lambda r: r.at)


def throttle_source(
    *,
    game: Callable[[], str | None] = running_game,
    sample: Callable[[], Window] = sample_window,
    now: Callable[[], float] = time.time,
) -> SourceResult:
    """Findings from the windows watched while a game ran, and the gap when none was.

    A window is sampled only when a known game is running right now: at the desktop a
    CPU limit costs nothing, and a limit seen there would be a finding about a machine
    nobody is using.
    """
    running = game()
    if running is not None:
        window = sample()
        record(running, window, attribute(window), at=now())

    latest, problems = remembered(now())
    if latest is None:
        return SourceResult(gaps=(Gap(SOURCE, NO_GAME_YET),))

    findings: list[Finding] = []
    for recorded in problems:
        findings.extend(findings_from(recorded.verdict, recorded.window))
    gaps = []
    if latest.verdict.kind == "unmeasured":
        gaps.append(Gap(SOURCE, latest.verdict.reason))
    return SourceResult(findings=tuple(findings), gaps=tuple(gaps))
