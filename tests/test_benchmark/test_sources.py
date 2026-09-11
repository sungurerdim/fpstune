"""The coverage number must count its failures, not just its successes.

"4 of 4 claims verified" is a true sentence and a false statement when the other
fifty-six were dropped before anyone counted. So the thing under test here is not
that the mapping is large — it is deliberately small — but that nothing falls out
of it silently.

Three failure modes, one class each:

* a metric a setting claims that nobody ever decided about
* a mapping pointing at a benchmark field that has since been renamed
* a claim that cannot be checked quietly vanishing instead of being reported
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from fpstune.benchmark.sources import (
    NO_DIRECTION,
    NO_INSTRUMENT,
    NOT_JUDGEABLE,
    NOT_QUANTIFIED,
    SOURCES,
    Source,
    coverage,
    source_for,
    why_unmeasurable,
)
from fpstune.benchmark.verify_round import claims_of, direction_of, parse_claim
from fpstune.settings.impact_categories import IGNORED_KEYS
from fpstune.settings.registry import SettingsRegistry


def _setting(setting_id: str = "test:one", **impact: object) -> SimpleNamespace:
    return SimpleNamespace(id=setting_id, impact_scores=dict(impact))


# The stats object each source reads its fields out of. Named here rather than
# imported inside the test so that deleting one of these classes is a collection
# error rather than a skipped assertion.
def _emitted_keys(source_name: str) -> set[str]:
    if source_name == "presentmon":
        from fpstune.benchmark.presentmon import FrameTimeStats

        # Three keys are gated on the run's own evidence (#74), so the union of
        # a GPU-bound and a CPU-bound run with input tracked is what the source
        # can ever see; a bare FrameTimeStats() emits none of them.
        gpu_bound = FrameTimeStats(
            fps_avg=60.0, cpu_busy_ms=8.0, gpu_time_ms=16.0, input_latency_ms=20.0
        )
        cpu_bound = FrameTimeStats(fps_avg=60.0, cpu_busy_ms=16.0, gpu_time_ms=8.0)
        return set(gpu_bound.to_dict()) | set(cpu_bound.to_dict())
    if source_name == "network":
        from fpstune.benchmark.network import LatencyStats

        return set(LatencyStats().to_dict())
    if source_name == "dpc":
        from fpstune.benchmark.dpc import DpcStats

        return set(DpcStats().to_dict())
    # The suite benches report through `BenchResult.readings`, keyed by the
    # metric name itself rather than by a stats field, so what has to still
    # exist is the reading. Run at the smallest size that still produces one.
    if source_name == "disk_io":
        from fpstune.benchmark.disk_io import DiskIoBench

        bench = DiskIoBench(file_mb=1, block_kb=64, random_reads=10)
        available, why = bench.is_available()
        if not available:
            pytest.skip(f"disk bench cannot run here: {why}")
        return set(bench.run(1).readings)
    if source_name == "memory":
        from fpstune.benchmark.memory import MemoryBench

        return set(MemoryBench(working_set_mb=1, chase_steps=1000).run(1).readings)
    if source_name == "boot_time":
        from unittest.mock import patch

        from fpstune.benchmark.boot_time import BootTimeBench

        # The log is replaced because it needs administrator rights to read;
        # what has to still exist is the reading `shutdown_speed` is mapped to.
        rows = [
            {"kind": "status", "access": "ok"},
            {"kind": "100", "at": 1_789_000_000, "boot_ms": 42_000, "main_path_ms": 30_000},
            {"kind": "200", "at": 1_788_900_000, "shutdown_ms": 9_500},
        ]
        with patch("fpstune.benchmark.boot_time.query_rows", return_value=(rows, "")):
            return set(BootTimeBench().run(2).readings)
    if source_name == "gpu_memory":
        from unittest.mock import patch

        from fpstune.benchmark.gpu_memory import GpuMemoryBench

        adapter = {"adapter": "luid_0x00000000_0x0679BD6A_phys_0", "dedicated": 939_376_640}
        with patch("fpstune.benchmark.gpu_memory.query_rows", return_value=([adapter], "")):
            return set(GpuMemoryBench().run(2).readings)
    if source_name == "process_sampler":
        from unittest.mock import patch

        from fpstune.benchmark.process_sampler import ProcessSamplerBench

        # The counters are replaced, the bench is not: a machine whose WMI is
        # slow would otherwise decide whether this test checked anything.
        second = {
            "total_cpu": 1653,
            "idle_cpu": 1418,
            "total_io": 4_016_661,
            "available_mb": 17066,
            "game_instances": 0,
        }
        with (
            patch("fpstune.benchmark.process_sampler.query_rows", return_value=([second], "")),
            patch("fpstune.benchmark.process_sampler.running_game", return_value=None),
        ):
            return set(ProcessSamplerBench(window_samples=1).run(2).readings)
    if source_name == "storage_health":
        from unittest.mock import patch

        from fpstune.benchmark.storage_health import StorageHealthBench

        # Elevation and the drive are both replaced; the bench is not. What has
        # to still exist is the reading, and on an unelevated machine the real
        # cmdlet would answer nothing and this test would pass by not looking.
        drive = {"unique_id": "eui.0025385A11B2C3D4", "wear": 4, "temperature": 41}
        with (
            patch("fpstune.benchmark.storage_health.is_admin", return_value=True),
            patch("fpstune.benchmark.storage_health.query_rows", return_value=([drive], "")),
        ):
            return set(StorageHealthBench().run(2).readings)
    if source_name == "event_scan":
        from unittest.mock import patch

        from fpstune.benchmark.event_scan import EventScanBench

        # The log query is replaced, the bench is not: what has to still exist
        # is the reading `crash_rate` is mapped to, and only the bench can say
        # whether it does. A machine with an empty log would otherwise decide
        # whether this test checked anything.
        row = {
            "whea": 0,
            "bugcheck": 1,
            "unexpected_shutdown": 0,
            "tdr": 0,
            "disk_errors": 0,
            "disk_providers": "",
            "log_from": 0,
        }
        with patch("fpstune.benchmark.event_scan.query_rows", return_value=([row], "")):
            return set(EventScanBench(window_days=1).run(2).readings)
    if source_name == "sensors":
        from unittest.mock import patch

        from fpstune.benchmark.sensors import SensorBench

        # The sampling window is replaced, the bench is not: a machine with no
        # NVIDIA driver would otherwise decide whether this test looked at
        # anything. The row is the shape `build_script` emits.
        row = {"gpu_temp": 61.0, "gpu_power": 118.5, "zone_dk": 3452, "nvidia": True}
        with patch("fpstune.benchmark.sensors.query_rows", return_value=([row], "")):
            return set(SensorBench(window_samples=1).run(2).readings)
    if source_name == "network_load":
        # Run for real, with both ends of the network replaced. Listing the
        # reading names here instead would make this test agree with itself
        # rather than with the bench, and a rename in `network_load.py` — the
        # exact drift this whole class guards against — would sail through.
        from unittest.mock import patch

        from fpstune.benchmark.network_load import NetworkLoadBench

        def _served(_url: str, cap: int, _seconds: float) -> tuple[int, float]:
            time.sleep(0.05)  # long enough for one probe to land under load
            return cap, 0.05

        # Both directions replaced. The upload leg reaches a third party too,
        # and a test that quietly posted eight megabytes to measure a mapping
        # would be spending the developer's line to check a dictionary.
        with (
            patch("fpstune.benchmark.network_load._tcp_rtt_ms", return_value=10.0),
            patch("fpstune.benchmark.network_load._download", _served),
            patch("fpstune.benchmark.network_load._upload", _served),
        ):
            bench = NetworkLoadBench(
                cap_bytes=1000, upload_cap_bytes=500, cap_seconds=1.0, probes=2, probe_interval=0
            )
            return set(bench.run(1).readings)
    raise AssertionError(f"no stats class known for source {source_name!r}")


class TestTheMappingStillPointsAtSomethingReal:
    @pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.name)
    def test_every_mapped_field_is_one_the_benchmark_emits(self, source: Source) -> None:
        """The rename that would silently stop a claim being checkable.

        `fps_avg` moving to `fps_mean` in presentmon.py would leave this mapping
        pointing at nothing, and the only symptom would be a coverage number
        quietly getting smaller.
        """
        emitted = _emitted_keys(source.name)
        missing = {metric: field for metric, field in source.fields.items() if field not in emitted}
        assert not missing, (
            f"{source.name} no longer emits {sorted(missing.values())} — "
            f"the claims {sorted(missing)} would stop being checkable"
        )

    @pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.name)
    def test_every_mapped_metric_has_a_known_direction(self, source: Source) -> None:
        """A metric with no direction cannot be judged, so mapping it is a trap.

        It would be counted as measurable, measured, and then reported as
        unverifiable anyway — a coverage number promising something the engine
        cannot deliver.
        """
        for metric in source.fields:
            assert direction_of(metric) is not None, metric

    def test_no_metric_is_claimed_by_two_instruments(self) -> None:
        """Two sources for one metric makes `source_for` order-dependent."""
        seen: set[str] = set()
        for source in SOURCES:
            overlap = seen & set(source.fields)
            assert not overlap, f"{source.name} also claims {overlap}"
            seen |= set(source.fields)

    def test_the_thermal_claims_are_measured_by_the_sensor_bench(self) -> None:
        """Heat is a performance category (consequence 4), so it has to be
        readable under the load a bench actually applies. FurMark answers "how
        hot under a load nobody plays at", which is a different question."""
        for metric in ("gpu_temp_c", "power_watts"):
            source = source_for(metric)
            assert source is not None
            assert source.name == "sensors", metric

    def test_no_claim_is_measured_by_a_power_virus(self) -> None:
        """C11 rule 6: a stress test is not a performance test. FurMark stays a
        panel of its own and verifies nothing."""
        assert "furmark" not in {source.name for source in SOURCES}

    def test_nothing_is_both_measurable_and_listed_as_having_no_instrument(self) -> None:
        for source in SOURCES:
            for metric in source.fields:
                assert metric not in NO_INSTRUMENT, (
                    f"{metric} is measured by {source.name} but still listed as unmeasurable"
                )


class TestEveryShippedMetricHasBeenDecidedAbout:
    def test_no_claim_in_the_registry_falls_through_unaccounted_for(self) -> None:
        """The guard against a new metric arriving with nobody deciding anything.

        Adding `{"gpu_hotspot_c": -4}` to a setting should force a choice: wire
        an instrument, or write down why there is not one. Without this, the
        third option is available and invisible — the claim just never appears
        in a report again.
        """
        undecided: dict[str, str] = {}
        for setting in SettingsRegistry(discover_dynamic=False).get_all():
            for claim in claims_of(setting):
                metric = claim.metric
                if metric in IGNORED_KEYS or metric in NO_INSTRUMENT:
                    continue
                if source_for(metric) is not None:
                    continue
                if direction_of(metric) is None:
                    continue  # a ceiling or a quality — NO_DIRECTION covers it
                undecided[metric] = setting.id

        assert not undecided, (
            "these metrics are directional and have no instrument and no recorded "
            f"reason: {undecided}"
        )

    def test_the_no_instrument_list_is_not_carrying_dead_entries(self) -> None:
        """A reason written for a metric nothing claims any more is stale text.

        It reads as an outstanding gap in the coverage report when it is not one.
        """
        claimed = {
            claim.metric
            for setting in SettingsRegistry(discover_dynamic=False).get_all()
            for claim in claims_of(setting)
        }
        stale = sorted(set(NO_INSTRUMENT) - claimed)
        assert not stale, f"NO_INSTRUMENT explains metrics nothing claims: {stale}"


class TestWhyAClaimCannotBeChecked:
    def test_a_claim_with_no_number_is_not_reported_as_a_missing_instrument(self) -> None:
        """A word where a number belongs is a to-do about the claim, not the build.

        `throughput` rather than `privacy`, which this used to say: privacy is
        not a measurement question at all and now reports as one of those. The
        example has to be a metric something here can actually measure, or the
        test passes for the wrong reason.
        """
        assert why_unmeasurable(parse_claim("s:x", "throughput", "high")) == NOT_QUANTIFIED

    def test_a_ceiling_is_reported_as_a_ceiling(self) -> None:
        assert why_unmeasurable(parse_claim("s:x", "fps_menu_ceiling", 90)) == NO_DIRECTION

    def test_a_missing_instrument_says_which_one_is_missing(self) -> None:
        """`gpu_performance` rather than `vram_mb`, which this used to say.

        Video memory became measurable the day the GPU counter bench landed, and
        an example that has an instrument passes this test for the wrong reason.
        The example has to be a metric that is quantified, directional, and still
        unmeasured — which is what a real gap looks like.
        """
        reason = why_unmeasurable(parse_claim("s:x", "gpu_performance", "+5%"))
        assert reason == NO_INSTRUMENT["gpu_performance"]
        assert reason != NOT_QUANTIFIED

    def test_a_measurable_claim_returns_no_reason(self) -> None:
        assert why_unmeasurable(parse_claim("s:x", "latency_ms", -3.0)) is None


class TestCoverageCountsWhatItCannotDo:
    def test_nothing_is_dropped(self) -> None:
        setting = _setting(
            "test:one",
            latency_ms=-3.0,  # measurable
            gpu_performance="+5%",  # no instrument
            fps_menu_ceiling=90,  # no direction
            stability="high",  # never collected as a claim at all
        )
        result = coverage([setting])

        # stability is not a claim, so three, not four.
        assert result.total == 3
        assert len(result.measurable) == 1
        assert len(result.unmeasurable) == 2

    def test_the_summary_leads_with_the_shortfall(self) -> None:
        result = coverage([_setting("test:one", latency_ms=-3.0, gpu_performance="+5%")])
        assert result.summary == "1 of 2 claims can be measured here; 1 are not"

    def test_measuring_nothing_says_so_plainly(self) -> None:
        result = coverage([_setting("test:one", gpu_performance="+5%")])
        assert result.summary == "None of the 1 claims can be measured on this machine"

    def test_a_setting_that_claims_nothing_measurable_is_not_an_error(self) -> None:
        assert coverage([_setting("test:one", stability="high")]).total == 0

    def test_it_names_what_the_user_would_have_to_arrange(self) -> None:
        """A coverage figure nobody can act on is trivia.

        Knowing that half the claims need a game running is the difference
        between "we cannot check this" and "start a match and we can".
        """
        result = coverage([_setting("test:one", fps="+5%", latency_ms=-3.0)])
        assert result.required_conditions == [
            "a game running and rendering frames",
            "a reachable host to measure against",
        ]

    def test_one_condition_is_listed_once_however_many_claims_need_it(self) -> None:
        result = coverage(
            [_setting("test:one", fps="+5%", fps_1_percent_low="+8%", stutter_count=-3.0)]
        )
        assert result.required_conditions == ["a game running and rendering frames"]

    def test_the_dictionary_carries_the_reasons_and_not_just_the_counts(self) -> None:
        """The report renders from this, so the reasons have to survive it."""
        payload = coverage([_setting("test:one", gpu_performance="+5%")]).to_dict()
        assert payload["unmeasurable"][0]["reason"] == NO_INSTRUMENT["gpu_performance"]


class TestAgainstTheRealRegistry:
    def test_the_shipped_coverage_is_reported_rather_than_assumed(self) -> None:
        """A record of where this actually stands, that fails if it collapses.

        Not a target. The honest number was low until PresentMon's bottleneck
        split landed (#74): `fps_gpu_bound` is the registry's most-claimed metric,
        so the day it became measurable the balance flipped. What this catches is
        the mapping breaking wholesale, which would otherwise show up as a report
        full of "not checked" that nobody reads as a regression.
        """
        settings = SettingsRegistry(discover_dynamic=False).get_all()
        result = coverage(settings)

        assert result.total > 300, f"only {result.total} claims found in the registry"
        assert result.measurable, "nothing in the registry is measurable at all"
        measurable_metrics = {claim.metric for claim, _ in result.measurable}
        assert {"fps", "fps_gpu_bound", "fps_cpu_bound"} <= measurable_metrics
        assert len(result.measurable) > len(result.unmeasurable), (
            "most claims are measurable since #74; a flip back means an instrument "
            "mapping broke wholesale, not that the registry changed"
        )


class TestAQualitativeClaimIsNotAGap:
    """C11 rule 4, and the reason it needed a rule.

    A hundred of the registry's claims are about privacy, audibility or what a
    player can tell apart. None of them states a number, and until this class
    existed every one was reported as "the claim states no number" — which reads
    as an oversight and put them on a to-do list nothing could ever take them
    off. The distinction is not cosmetic: it is the difference between a
    shortfall a release can close and a category error.
    """

    def test_a_privacy_claim_is_named_for_what_it_is(self) -> None:
        claim = parse_claim("test:one", "privacy", "improved")

        reason = why_unmeasurable(claim)

        assert reason == NOT_JUDGEABLE["privacy"]
        assert reason != NOT_QUANTIFIED

    def test_it_wins_over_the_missing_number(self) -> None:
        """Order is the substance. Asked "did somebody forget a number" first,
        a privacy claim answers yes and joins a queue it cannot leave."""
        assert (
            why_unmeasurable(parse_claim("t:1", "footstep_clarity", "improved")) != NOT_QUANTIFIED
        )

    def test_it_wins_even_when_somebody_did_write_a_number(self) -> None:
        """`{"privacy": 5}` is still not a question a measurement settles."""
        reason = why_unmeasurable(parse_claim("t:1", "privacy", 5))

        assert reason == NOT_JUDGEABLE["privacy"]

    def test_coverage_counts_them_apart_from_the_gaps(self) -> None:
        """Counting them together produces a number that can only be improved by
        deleting the claims several settings exist for."""
        result = coverage(
            [
                _setting("t:1", privacy="improved"),
                _setting("t:2", gpu_performance="+5%"),
            ]
        )

        assert len(result.not_judgeable) == 1
        assert len(result.gaps) == 1
        assert len(result.unmeasurable) == 2

    def test_the_payload_says_which_ones_are_to_dos(self) -> None:
        payload = coverage([_setting("t:1", privacy="improved")]).to_dict()

        assert payload["unmeasurable"][0]["judgeable"] is False
        assert payload["not_judgeable_count"] == 1
        assert payload["gap_count"] == 0

    def test_the_summary_does_not_call_them_a_shortfall(self) -> None:
        summary = coverage([_setting("t:1", ux="improved")]).summary

        assert "not the kind of claim a measurement settles" in summary

    @pytest.mark.parametrize("metric", sorted(NOT_JUDGEABLE))
    def test_none_of_them_has_a_direction(self, metric: str) -> None:
        """A metric with a direction is scoreable, which is the opposite of the
        reason it would be on this list."""
        assert direction_of(metric) is None

    def test_nothing_is_both_unjudgeable_and_a_missing_instrument(self) -> None:
        """The two lists say incompatible things: one that an instrument would
        settle it, the other that nothing ever could."""
        overlap = sorted(set(NOT_JUDGEABLE) & set(NO_INSTRUMENT))

        assert not overlap, overlap

    def test_nothing_measurable_is_listed_as_unjudgeable(self) -> None:
        for source in SOURCES:
            for metric in source.fields:
                assert metric not in NOT_JUDGEABLE, (
                    f"{metric} is measured by {source.name} and cannot also be "
                    "the kind of claim nothing settles"
                )


class TestWhatIsMissingIsTheBindingThing:
    """When a claim lacks both a number and an instrument, say which matters.

    `{"startup_speed": "slower"}` is missing both. Writing `+2s` into it would
    change nothing, because what those claims time is a game launching and what
    this build times is Windows booting — so reporting "states no number" sends
    somebody to do work that closes no gap.

    The example used to be `shutdown_speed`, which stopped fitting the day the
    boot log became an instrument: a machine's shutdown is timed now, so that
    claim really is only missing its number.
    """

    def test_a_metric_with_no_instrument_says_so_rather_than_no_number(self) -> None:
        reason = why_unmeasurable(parse_claim("t:1", "startup_speed", "slower"))

        assert reason == NO_INSTRUMENT["startup_speed"]

    def test_the_half_that_now_has_an_instrument_asks_for_its_number(self) -> None:
        """`shutdown_speed` is timed by event 200, so "faster" is a real to-do."""
        assert source_for("shutdown_speed") is not None
        assert why_unmeasurable(parse_claim("t:1", "shutdown_speed", "faster")) == NOT_QUANTIFIED

    def test_a_metric_with_an_instrument_asks_for_the_number(self) -> None:
        """`throughput` is measurable since the network-load bench landed, so a
        word where a number belongs is exactly the to-do it reads as."""
        assert source_for("throughput") is not None
        assert why_unmeasurable(parse_claim("t:1", "throughput", "high")) == NOT_QUANTIFIED

    def test_a_ceiling_still_reports_as_a_ceiling(self) -> None:
        """It is quantified and has an instrument-less metric, so the ordering
        has to let it past both checks to reach the reason that fits."""
        assert why_unmeasurable(parse_claim("t:1", "fps_menu_ceiling", 90)) == NO_DIRECTION
