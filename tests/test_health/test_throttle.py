"""Which part was held back, from what Windows measured — and what is never guessed.

The owner's case: a player got under half the machine's capacity in a game, suspected the
CPU was overheating, and could not confirm it. CPU temperature is not readable without a
kernel driver, so this attributes the *effect*: the processor held below its own nominal
performance while it had work, and then the evidence for heat (a thermal zone passively
throttling) or for power (the power plan's cap, the battery) — or, when the limit is
there and neither is, an unmeasured cause that is said to be unmeasured.

One test per verdict, plus the rules between them:

* heat needs a thermal zone's own passive limit, power needs the plan's cap or the battery;
* event 37 says the firmware held the CPU, not why, so on its own it is an unmeasured cause;
* a GPU's power governor at full load (`sw_power_cap`) is not a throttle;
* a limit on a CPU with nothing to do is not a limit that cost frames;
* every signal that could not be read is named, and blocks `none`.
"""

from __future__ import annotations

from typing import Any

import pytest

from fpstune.benchmark.event_scan import FirmwareLimit
from fpstune.benchmark.presentmon import FrameTimeStats
from fpstune.health import throttle
from fpstune.health.model import Finding, Gap, Quantity
from fpstune.health.pdh import CPU_BUSY, CPU_PERFORMANCE, CPU_PERFORMANCE_LIMIT, ZONE_PASSIVE_LIMIT
from fpstune.health.power_state import PowerState
from fpstune.health.throttle import (
    COUNTERS_UNAVAILABLE,
    GPU_NO_REASONS,
    GPU_VENDOR_GAP,
    LIMIT_SHARE,
    LOADED_PROCESSORS,
    NO_GAME_YET,
    NOMINAL_PERCENT,
    PROBLEM_MEMORY_SECONDS,
    FrameSide,
    GpuSample,
    Sample,
    Window,
    attribute,
    findings_from,
    frame_side,
    sample_window,
    throttle_source,
)

_START, _END = 1_790_000_000.0, 1_790_000_006.0
_NVIDIA = "PCI\\VEN_10DE&DEV_249D"
_AC = PowerState(on_battery=False, processor_cap_percent=100)


def _sample(
    busy: float = 60.0, performance: float = 150.0, limit: float = 100.0, passive: float = 100.0
) -> Sample:
    return Sample(busy, performance, limit, passive)


def _gpu(*reasons: str) -> GpuSample:
    return GpuSample(frozenset(reasons))


def _window(
    samples: list[Sample] | None = None,
    gpu: list[GpuSample] | None = None,
    **overrides: Any,
) -> Window:
    fields: dict[str, Any] = {
        "started_at": _START,
        "ended_at": _END,
        "samples": tuple(samples if samples is not None else [_sample()] * 6),
        "gpu_samples": tuple(gpu if gpu is not None else [_gpu("gpu_idle")] * 3),
        "gpu_device_id": _NVIDIA,
        "firmware_limits": (),
        "power": _AC,
        "logical_processors": 16,
    }
    fields.update(overrides)
    return Window(**fields)


class TestNone:
    def test_a_machine_whose_cpu_and_gpu_are_not_held_back_says_so_with_its_numbers(self) -> None:
        verdict = attribute(_window())

        assert verdict.kind == "none"
        assert "whatever held the frame rate down was not the processor" in verdict.reason
        assert verdict.evidence["cpu_performance_limit_percent"] == 100.0
        assert verdict.evidence["cpu_performance_percent"] == 150.0
        assert findings_from(verdict, _window()) == []

    def test_a_gpu_power_cap_at_full_load_is_the_governor_not_a_throttle(self) -> None:
        verdict = attribute(_window(gpu=[_gpu("sw_power_cap")] * 3))

        assert verdict.kind == "none"

    def test_one_throttled_reading_in_three_is_a_blip_not_the_window(self) -> None:
        gpu = [_gpu("hw_thermal_slowdown"), _gpu(), _gpu()]

        assert attribute(_window(gpu=gpu)).kind == "none"

    def test_a_cpu_with_nothing_to_do_cannot_have_lost_frames_to_a_limit(self) -> None:
        idle = [_sample(busy=1.0, limit=60.0)] * 6

        verdict = attribute(_window(samples=idle))

        assert verdict.kind == "none"
        assert "not busy enough" in verdict.reason

    def test_boost_above_nominal_is_not_a_limit(self) -> None:
        boosting = [_sample(performance=174.0, limit=100.0)] * 6

        assert attribute(_window(samples=boosting)).kind == "none"


class TestCpuThermal:
    def test_a_limited_cpu_with_a_thermal_zone_passively_throttling_is_heat(self) -> None:
        hot = [_sample(limit=48.0, passive=35.0)] * 6

        verdict = attribute(_window(samples=hot))

        assert verdict.kind == "cpu_thermal"
        assert "heat, by Windows' own account" in verdict.reason
        assert verdict.evidence["cpu_performance_limit_percent"] == 48.0
        assert verdict.evidence["thermal_zone_limiting"] is True

    def test_it_becomes_a_cpu_finding_with_the_measured_limit_against_nominal(self) -> None:
        window = _window(samples=[_sample(limit=48.0, passive=35.0)] * 6)

        findings = findings_from(attribute(window), window)

        assert findings == [
            Finding(
                "cpu",
                None,
                "warning",
                "health.cpu.throttled_thermal",
                Quantity(48.0, "%"),
                Quantity(NOMINAL_PERCENT, "%"),
                "throttle",
            )
        ]

    def test_a_zone_throttling_while_the_cpu_is_not_limited_is_not_a_cpu_verdict(self) -> None:
        """The zone may control something other than the processors: no limit, no verdict."""
        samples = [_sample(limit=100.0, passive=40.0)] * 6

        assert attribute(_window(samples=samples)).kind == "none"

    def test_half_the_window_is_enough_and_less_is_not(self) -> None:
        half = [_sample(limit=60.0, passive=40.0)] * 3 + [_sample()] * 3
        under = [_sample(limit=60.0, passive=40.0)] * 2 + [_sample()] * 4

        assert LIMIT_SHARE == 0.5
        assert attribute(_window(samples=half)).kind == "cpu_thermal"
        assert attribute(_window(samples=under)).kind == "none"

    def test_the_lowest_zone_decides_because_any_zone_restricting_counts(self) -> None:
        sample = Sample(60.0, 90.0, 60.0, passive_limit_percent=40.0)

        assert attribute(_window(samples=[sample] * 6)).kind == "cpu_thermal"


class TestCpuPowerLimit:
    def test_a_power_plan_that_caps_the_processor_is_the_reason_not_heat(self) -> None:
        """The 'under half of capacity' case with nothing wrong in the hardware."""
        capped = [_sample(limit=50.0, passive=100.0)] * 6

        verdict = attribute(_window(samples=capped, power=PowerState(False, 50)))

        assert verdict.kind == "cpu_power_limit"
        assert "caps the processor at 50 %" in verdict.reason

    def test_the_finding_reads_the_plans_cap_as_the_number_that_explains_it(self) -> None:
        window = _window(samples=[_sample(limit=50.0)] * 6, power=PowerState(False, 50))

        (finding,) = findings_from(attribute(window), window)

        assert (finding.title_key, finding.reading) == (
            "health.cpu.throttled_power",
            Quantity(50.0, "%"),
        )

    def test_a_limited_cpu_on_battery_is_a_power_limit(self) -> None:
        verdict = attribute(_window(samples=[_sample(limit=70.0)] * 6, power=PowerState(True, 100)))

        assert verdict.kind == "cpu_power_limit"
        assert "running on battery" in verdict.reason

    def test_a_plan_cap_with_no_limit_actually_in_force_is_nothing_to_report(self) -> None:
        """The cap exists, the counter says the CPU was not held back: no verdict."""
        verdict = attribute(_window(power=PowerState(False, 50)))

        assert verdict.kind == "none"

    def test_thermal_and_power_together_name_one_and_list_the_other(self) -> None:
        both = [_sample(limit=40.0, passive=30.0)] * 6

        verdict = attribute(_window(samples=both, power=PowerState(False, 50)))

        assert (verdict.kind, verdict.also) == ("cpu_thermal", ("cpu_power_limit",))
        window = _window(samples=both, power=PowerState(False, 50))
        assert [f.title_key for f in findings_from(verdict, window)] == [
            "health.cpu.throttled_thermal",
            "health.cpu.throttled_power",
        ]


class TestTheCauseThatCannotBeNamed:
    """Event 37 and the limit counter say *that*, not *why*: the cause is not guessed."""

    def test_a_limited_cpu_on_ac_with_no_zone_throttling_and_no_cap_is_an_unmeasured_cause(
        self,
    ) -> None:
        limited = [_sample(limit=62.0, passive=100.0)] * 6

        verdict = attribute(_window(samples=limited))

        assert verdict.kind == "unmeasured"
        assert "not guessed" in verdict.reason
        assert "whether heat or power did it" in verdict.reason
        assert verdict.evidence["cpu_limited_cause_unknown"] is True

    def test_the_effect_is_still_a_finding_even_though_the_cause_is_not(self) -> None:
        window = _window(samples=[_sample(limit=62.0)] * 6)

        (finding,) = findings_from(attribute(window), window)

        assert finding.title_key == "health.cpu.throttled_unknown_cause"
        assert finding.reading == Quantity(62.0, "%")

    def test_an_event_37_inside_the_window_alone_is_an_unmeasured_cause_too(self) -> None:
        event = FirmwareLimit(ended_at=_END, duration_seconds=300.0)

        verdict = attribute(_window(firmware_limits=(event,)))

        assert verdict.kind == "unmeasured"
        assert verdict.evidence["firmware_limit_events"] == 1
        assert "firmware limit events cover the window" in verdict.reason

    def test_an_event_written_after_the_window_still_covers_it(self) -> None:
        """Event 37 is late evidence: written once the cap had lasted a while."""
        late = FirmwareLimit(ended_at=_END + 240.0, duration_seconds=300.0)

        assert attribute(_window(firmware_limits=(late,))).kind == "unmeasured"

    def test_an_event_that_ended_before_the_window_began_is_not_this_window(self) -> None:
        earlier = FirmwareLimit(ended_at=_START - 5.0, duration_seconds=300.0)

        assert attribute(_window(firmware_limits=(earlier,))).kind == "none"

    def test_an_event_during_a_window_where_the_cpu_was_idle_is_not_a_lost_frame(self) -> None:
        event = FirmwareLimit(ended_at=_END, duration_seconds=300.0)
        idle = [_sample(busy=0.5)] * 6

        assert attribute(_window(samples=idle, firmware_limits=(event,))).kind == "none"

    def test_an_event_with_a_thermal_zone_throttling_is_named_heat(self) -> None:
        event = FirmwareLimit(ended_at=_END, duration_seconds=300.0)
        samples = [_sample(limit=100.0, passive=40.0)] * 6

        verdict = attribute(_window(samples=samples, firmware_limits=(event,)))

        assert verdict.kind == "cpu_thermal"


class TestGpu:
    @pytest.mark.parametrize(
        "reason",
        ["hw_thermal_slowdown", "sw_thermal_slowdown", "hw_slowdown", "hw_power_brake_slowdown"],
    )
    def test_a_driver_reported_limit_for_most_of_the_window_is_a_gpu_verdict(
        self, reason: str
    ) -> None:
        verdict = attribute(_window(gpu=[_gpu(reason)] * 3))

        assert verdict.kind == "gpu_thermal_or_power"
        assert reason in verdict.reason

    def test_it_becomes_a_finding_under_the_gpu_that_was_read(self) -> None:
        window = _window(gpu=[_gpu("hw_thermal_slowdown")] * 3)

        (finding,) = findings_from(attribute(window), window)

        assert (finding.component, finding.device_id, finding.title_key) == (
            "gpu",
            _NVIDIA,
            "health.gpu.throttled",
        )

    @pytest.mark.parametrize(
        "reason", ["gpu_idle", "sw_power_cap", "applications_clocks_setting", "sync_boost"]
    )
    def test_reasons_that_are_not_heat_or_a_power_brake_are_not_a_limit(self, reason: str) -> None:
        assert attribute(_window(gpu=[_gpu(reason)] * 3)).kind == "none"


class TestTheFrameSideBreaksTies:
    _hot_cpu = [_sample(limit=40.0, passive=30.0)] * 6
    _hot_gpu = [_gpu("hw_thermal_slowdown")] * 3

    def test_with_no_capture_the_cpu_goes_first(self) -> None:
        verdict = attribute(_window(samples=self._hot_cpu, gpu=self._hot_gpu))

        assert (verdict.kind, verdict.also) == ("cpu_thermal", ("gpu_thermal_or_power",))

    def test_a_gpu_bound_frame_puts_the_gpu_first(self) -> None:
        window = _window(
            samples=self._hot_cpu, gpu=self._hot_gpu, frame=FrameSide(fps=41.0, bottleneck="gpu")
        )

        verdict = attribute(window)

        assert (verdict.kind, verdict.also) == ("gpu_thermal_or_power", ("cpu_thermal",))
        assert verdict.evidence["frame_bottleneck"] == "gpu"

    def test_a_cpu_bound_frame_keeps_the_cpu_first(self) -> None:
        window = _window(
            samples=self._hot_cpu, gpu=self._hot_gpu, frame=FrameSide(fps=41.0, bottleneck="cpu")
        )

        assert attribute(window).kind == "cpu_thermal"

    def test_the_frame_side_comes_from_presentmons_own_statistics(self) -> None:
        stats = FrameTimeStats(fps_avg=41.5, cpu_busy_ms=9.0, gpu_time_ms=22.0)

        assert frame_side(stats) == FrameSide(fps=41.5, bottleneck="gpu")

    def test_the_frame_side_never_creates_a_verdict_by_itself(self) -> None:
        window = _window(frame=FrameSide(fps=20.0, bottleneck="gpu"))

        assert attribute(window).kind == "none"


class TestUnmeasured:
    def test_no_counters_is_unmeasured_and_never_none(self) -> None:
        verdict = attribute(_window(samples=[]))

        assert verdict.kind == "unmeasured"
        assert COUNTERS_UNAVAILABLE in verdict.reason

    def test_a_cpu_that_is_clean_on_a_machine_whose_gpu_cannot_be_read_is_unmeasured(self) -> None:
        """Without an NVIDIA driver the GPU cannot be ruled out: that is not 'none'."""
        window = _window(gpu=[], gpu_reason=GPU_VENDOR_GAP)

        verdict = attribute(window)

        assert verdict.kind == "unmeasured"
        assert verdict.reason == GPU_VENDOR_GAP

    def test_the_gpu_tool_failing_says_why_and_blocks_none(self) -> None:
        verdict = attribute(_window(gpu=[], gpu_reason="nvidia-smi did not answer"))

        assert verdict.kind == "unmeasured"
        assert "nvidia-smi did not answer" in verdict.reason

    def test_a_gpu_driver_that_reported_no_reasons_is_unmeasured_not_clean(self) -> None:
        verdict = attribute(_window(gpu=[GpuSample(None)] * 3, gpu_reason=""))

        assert verdict.kind == "unmeasured"
        assert verdict.reason == GPU_NO_REASONS

    def test_a_limited_cpu_is_named_even_when_the_gpu_could_not_be_read(self) -> None:
        window = _window(
            samples=[_sample(limit=40.0, passive=30.0)] * 6, gpu=[], gpu_reason=GPU_VENDOR_GAP
        )

        assert attribute(window).kind == "cpu_thermal"

    def test_both_missing_names_both(self) -> None:
        verdict = attribute(_window(samples=[], gpu=[], gpu_reason=GPU_VENDOR_GAP))

        assert COUNTERS_UNAVAILABLE in verdict.reason and GPU_VENDOR_GAP in verdict.reason

    def test_an_unreadable_event_log_is_recorded_but_does_not_block_the_live_counters(
        self,
    ) -> None:
        verdict = attribute(_window(firmware_limits=None))

        assert verdict.kind == "none"
        assert verdict.evidence["firmware_events_unreadable"] is True
        assert verdict.evidence["firmware_limit_events"] is None

    def test_unknown_processor_count_cannot_tie_a_limit_to_work(self) -> None:
        verdict = attribute(_window(logical_processors=None))

        assert verdict.kind == "unmeasured"
        assert "could not be read" in verdict.reason


class TestHowBusyIsBusyEnough:
    def test_one_processors_worth_of_work_counts_on_any_core_count(self) -> None:
        assert LOADED_PROCESSORS == 1.0
        for processors in (4, 16, 24):
            busy = 100.0 / processors + 1e-9  # one logical processor's worth
            window = _window(
                samples=[_sample(busy=busy, limit=60.0, passive=40.0)] * 6,
                logical_processors=processors,
            )
            assert attribute(window).kind == "cpu_thermal", processors

    def test_just_under_one_processors_worth_does_not(self) -> None:
        window = _window(samples=[_sample(busy=100.0 / 16 - 0.1, limit=60.0, passive=40.0)] * 6)

        assert attribute(window).kind == "none"


class _FakeCounters:
    def __init__(self, rows: list[dict[str, list[float]]]) -> None:
        self.rows = rows
        self.closed = False

    def read(self) -> dict[str, list[float]]:
        return self.rows.pop(0) if self.rows else {}

    def close(self) -> None:
        self.closed = True


def _row(busy: float = 60.0, limit: float = 100.0, passive: tuple[float, ...] = (100.0, 100.0)):
    return {
        "performance": [150.0],
        "limit": [limit],
        "busy": [busy],
        "passive": list(passive),
    }


class TestSampling:
    def _sample(self, **overrides: Any) -> tuple[Window, list[float], _FakeCounters]:
        counters = _FakeCounters(overrides.pop("rows", [_row() for _ in range(6)]))
        slept: list[float] = []
        ticks = iter([_START, _END])
        defaults: dict[str, Any] = {
            "open_counters": lambda: counters,
            "read_gpu": lambda: (GpuSample(frozenset({"gpu_idle"})), _NVIDIA, ""),
            "read_events": lambda _since: ([], ""),
            "read_power": lambda: _AC,
            "logical_processors": 16,
            "clock": lambda: next(ticks),
            "sleep": slept.append,
        }
        defaults.update(overrides)
        return sample_window(**defaults), slept, counters

    def test_it_reads_the_counters_once_a_second_for_the_whole_window(self) -> None:
        window, slept, counters = self._sample()

        assert len(window.samples) == 6
        assert slept == [1.0] * 6
        assert counters.closed

    def test_a_sample_is_the_means_of_the_instances_and_the_lowest_zone(self) -> None:
        window, _slept, _counters = self._sample(rows=[_row(passive=(100.0, 35.0))] * 6)

        assert window.samples[0] == Sample(60.0, 150.0, 100.0, 35.0)

    def test_the_gpus_reasons_are_read_three_times_beside_the_counters(self) -> None:
        window, _slept, _counters = self._sample()

        assert len(window.gpu_samples) == 3
        assert window.gpu_device_id == _NVIDIA
        assert window.gpu_reason == ""

    def test_a_gpu_tool_that_cannot_answer_leaves_its_reason_and_no_samples(self) -> None:
        window, _slept, _counters = self._sample(read_gpu=lambda: (None, None, GPU_VENDOR_GAP))

        assert window.gpu_samples == () and window.gpu_reason == GPU_VENDOR_GAP

    def test_the_event_log_is_asked_from_the_start_of_the_window(self) -> None:
        asked: list[float] = []

        def events(since: float):
            asked.append(since)
            return [FirmwareLimit(_END, 120.0)], ""

        window, _slept, _counters = self._sample(read_events=events)

        assert asked == [_START]
        assert window.firmware_limits == (FirmwareLimit(_END, 120.0),)

    def test_an_unreadable_event_log_is_none_not_an_empty_tuple(self) -> None:
        window, _slept, _counters = self._sample(read_events=lambda _s: ([], "the log is locked"))

        assert window.firmware_limits is None

    def test_counters_that_cannot_be_opened_give_no_samples_and_the_window_is_unmeasured(
        self,
    ) -> None:
        def broken() -> _FakeCounters:
            raise OSError("pdh.dll")

        window, _slept, _counters = self._sample(open_counters=broken)

        assert window.samples == ()
        assert attribute(window).kind == "unmeasured"

    def test_the_caller_can_attach_the_frame_side_of_a_capture(self) -> None:
        side = FrameSide(fps=41.0, bottleneck="gpu")

        window, _slept, _counters = self._sample(frame=side)

        assert window.frame == side

    def test_the_counter_paths_are_the_english_ones(self) -> None:
        assert throttle._COUNTERS == {
            "performance": CPU_PERFORMANCE,
            "limit": CPU_PERFORMANCE_LIMIT,
            "busy": CPU_BUSY,
            "passive": ZONE_PASSIVE_LIMIT,
        }


class TestTheSource:
    @pytest.fixture(autouse=True)
    def _forget(self):
        throttle.reset()
        yield
        throttle.reset()

    @staticmethod
    def _hot() -> Window:
        return _window(samples=[_sample(limit=48.0, passive=35.0)] * 6)

    def test_with_no_game_ever_seen_the_gap_says_in_game_throttling_was_not_measured(self) -> None:
        result = throttle_source(game=lambda: None, sample=lambda: pytest.fail("sampled"))

        assert result.findings == ()
        assert result.gaps == (Gap("throttle", NO_GAME_YET),)

    def test_a_running_game_gets_a_window_sampled_and_judged(self) -> None:
        result = throttle_source(game=lambda: "cod26", sample=self._hot, now=lambda: 100.0)

        assert [f.title_key for f in result.findings] == ["health.cpu.throttled_thermal"]
        assert result.gaps == ()

    def test_a_clean_window_while_playing_is_no_findings_and_no_gaps(self) -> None:
        result = throttle_source(game=lambda: "cod26", sample=_window, now=lambda: 100.0)

        assert result == throttle.SourceResult()

    def test_the_problem_outlives_the_game_so_it_can_be_read_after_the_match(self) -> None:
        throttle_source(game=lambda: "cod26", sample=self._hot, now=lambda: 100.0)

        later = throttle_source(
            game=lambda: None, sample=lambda: pytest.fail("sampled"), now=lambda: 100.0 + 600.0
        )

        assert [f.title_key for f in later.findings] == ["health.cpu.throttled_thermal"]

    def test_it_is_forgotten_after_the_memory_so_a_fix_is_not_contradicted_forever(self) -> None:
        throttle_source(game=lambda: "cod26", sample=self._hot, now=lambda: 100.0)

        gone = throttle_source(
            game=lambda: None,
            sample=lambda: pytest.fail("sampled"),
            now=lambda: 100.0 + PROBLEM_MEMORY_SECONDS + 1,
        )

        assert gone.findings == ()

    def test_a_later_clean_window_does_not_erase_an_earlier_problem(self) -> None:
        throttle_source(game=lambda: "cod26", sample=self._hot, now=lambda: 100.0)

        result = throttle_source(game=lambda: "cod26", sample=_window, now=lambda: 160.0)

        assert [f.title_key for f in result.findings] == ["health.cpu.throttled_thermal"]

    def test_an_unmeasured_latest_window_is_a_gap_beside_any_earlier_problem(self) -> None:
        throttle_source(game=lambda: "cod26", sample=self._hot, now=lambda: 100.0)

        result = throttle_source(
            game=lambda: "cod26", sample=lambda: _window(samples=[]), now=lambda: 160.0
        )

        assert [f.title_key for f in result.findings] == ["health.cpu.throttled_thermal"]
        assert [g.source for g in result.gaps] == ["throttle"]

    def test_the_unknown_cause_window_is_a_finding_and_a_gap_both(self) -> None:
        result = throttle_source(
            game=lambda: "cod26",
            sample=lambda: _window(samples=[_sample(limit=62.0)] * 6),
            now=lambda: 100.0,
        )

        assert [f.title_key for f in result.findings] == ["health.cpu.throttled_unknown_cause"]
        assert "not guessed" in result.gaps[0].reason


def test_the_verdict_kinds_are_exactly_the_five_the_issue_names() -> None:
    assert set(throttle.VerdictKind.__args__) == {  # type: ignore[attr-defined]
        "cpu_thermal",
        "cpu_power_limit",
        "gpu_thermal_or_power",
        "none",
        "unmeasured",
    }
