"""Tests for reading where a frame's time actually went — and for what that is allowed to claim.

A frame rate on its own is a number with no cause attached: 57 fps says nothing
about whether lowering a shadow setting would help. PresentMon 2.x reports the
CPU and GPU cost of every frame, the input-to-photon latency when asked, and the
presentation path each frame took. The parser reads all of it; what it may then
*say* is narrower than what it read.

Two PresentMon caveats shape the verdicts (#74). Issue #222: ``MsCPUBusy`` can
equal the frame time on a GPU-bound system, so two costs inside the 10% band are
*unknown*, never "both" — the dev-machine reading of CPU 17.18 ms against GPU
17.33 ms that once read as "both sides saturated" is exactly that shape. And a
key an instrument did not establish is absent from its output rather than zero:
``fps_gpu_bound`` exists only from a GPU-bound run, ``input_latency_ms`` only when
input was tracked, so a claim is never judged against a run that did not
measure it (C11).
"""

from __future__ import annotations

import pytest

from fpstune.benchmark.presentmon import (
    PRESENT_MODE_COLUMNS,
    STUTTER_THRESHOLD_FACTOR,
    FrameTimeStats,
    PresentMonBenchmark,
)

# Column names as PresentMon 2.5.1 writes them, trimmed to what is read.
HEADER = (
    "Application,MsBetweenPresents,MsCPUBusy,MsGPUTime,MsGPUWait,"
    "MsAllInputToPhotonLatency,TimeInMs\n"
)
HEADER_WITH_MODE = (
    "Application,MsBetweenPresents,MsCPUBusy,MsGPUTime,MsGPUWait,"
    "MsAllInputToPhotonLatency,TimeInMs,PresentMode\n"
)


def _capture(tmp_path, rows: str, header: str = HEADER):
    path = tmp_path / "capture.csv"
    path.write_text(header + rows, encoding="utf-8")
    return path


class TestTheBottleneckVerdict:
    def test_a_slower_gpu_is_gpu_bound(self) -> None:
        stats = FrameTimeStats(cpu_busy_ms=8.0, gpu_time_ms=16.0)
        assert stats.bottleneck == "gpu"

    def test_a_slower_cpu_is_cpu_bound(self) -> None:
        stats = FrameTimeStats(cpu_busy_ms=16.0, gpu_time_ms=8.0)
        assert stats.bottleneck == "cpu"

    def test_two_costs_inside_the_band_are_unknown_not_both(self) -> None:
        """The measured case, and PresentMon #222's shape: CPU busy equal to the
        frame time on a GPU-bound machine. Calling it "both" states a fact the
        instrument cannot support; calling it GPU-bound because the GPU is a hair
        higher would send a user to change settings that cannot help them."""
        stats = FrameTimeStats(cpu_busy_ms=17.18, gpu_time_ms=17.33)
        assert stats.bottleneck == "unknown"

    @pytest.mark.parametrize(
        ("cpu", "gpu", "expected"),
        [
            (10.0, 10.9, "unknown"),  # inside the band
            (10.0, 11.1, "gpu"),  # just outside it
            (10.9, 10.0, "unknown"),
            (11.1, 10.0, "cpu"),
        ],
    )
    def test_the_band_is_where_the_verdict_changes(
        self, cpu: float, gpu: float, expected: str
    ) -> None:
        assert FrameTimeStats(cpu_busy_ms=cpu, gpu_time_ms=gpu).bottleneck == expected

    def test_a_capture_without_the_breakdown_says_unknown(self) -> None:
        """An older PresentMon reports no CPU/GPU split. That is not a
        bottleneck of zero — it is no answer, and must not read as one."""
        assert FrameTimeStats(fps_avg=120.0).bottleneck == "unknown"
        assert FrameTimeStats(cpu_busy_ms=10.0).bottleneck == "unknown"
        assert FrameTimeStats(gpu_time_ms=10.0).bottleneck == "unknown"

    def test_both_is_no_longer_a_verdict_this_instrument_produces(self) -> None:
        for cpu, gpu in ((10.0, 10.0), (17.18, 17.33), (0.0, 0.0), (8.0, 16.0), (16.0, 8.0)):
            assert FrameTimeStats(cpu_busy_ms=cpu, gpu_time_ms=gpu).bottleneck != "both"


class TestWhatTheRunIsAllowedToClaim:
    """The gated keys of `to_dict()` — present only on the instrument's own evidence."""

    def test_a_gpu_bound_run_offers_its_frame_rate_as_gpu_bound_only(self) -> None:
        payload = FrameTimeStats(fps_avg=57.4, cpu_busy_ms=8.0, gpu_time_ms=16.0).to_dict()
        assert payload["fps_gpu_bound"] == 57.4
        assert "fps_cpu_bound" not in payload

    def test_a_cpu_bound_run_offers_its_frame_rate_as_cpu_bound_only(self) -> None:
        payload = FrameTimeStats(fps_avg=144.0, cpu_busy_ms=16.0, gpu_time_ms=8.0).to_dict()
        assert payload["fps_cpu_bound"] == 144.0
        assert "fps_gpu_bound" not in payload

    def test_an_unknown_run_offers_neither(self) -> None:
        """The #74 gate: MsCPUBusy equal to the frame time yields no side at all,
        so `verify_round` reports the claim unmeasured instead of judging it."""
        payload = FrameTimeStats(fps_avg=57.4, cpu_busy_ms=17.4, gpu_time_ms=17.4).to_dict()
        assert payload["bottleneck"] == "unknown"
        assert "fps_gpu_bound" not in payload
        assert "fps_cpu_bound" not in payload

    def test_input_latency_is_a_key_only_when_it_was_tracked(self) -> None:
        """PresentMon reports input-to-photon only with --track_input; the 0.0
        default is 'not tracked', and must never read as a measured zero."""
        assert "input_latency_ms" not in FrameTimeStats(fps_avg=60.0).to_dict()
        assert FrameTimeStats(input_latency_ms=18.828).to_dict()["input_latency_ms"] == 18.828

    def test_the_present_mode_is_a_key_only_when_the_column_was_there(self) -> None:
        assert "present_mode" not in FrameTimeStats().to_dict()
        payload = FrameTimeStats(present_mode="Hardware: Independent Flip").to_dict()
        assert payload["present_mode"] == "Hardware: Independent Flip"


class TestParsingACapture:
    def test_the_breakdown_is_read_from_the_csv(self, tmp_path) -> None:
        capture = _capture(
            tmp_path,
            "cod26-cod.exe,16.0,8.0,15.0,0.5,20.0,100.0\n"
            "cod26-cod.exe,16.0,8.0,15.0,0.5,20.0,116.0\n",
        )

        stats = PresentMonBenchmark().analyze_capture(capture)

        assert stats is not None
        assert stats.cpu_busy_ms == pytest.approx(8.0)
        assert stats.gpu_time_ms == pytest.approx(15.0)
        assert stats.gpu_wait_ms == pytest.approx(0.5)
        assert stats.input_latency_ms == pytest.approx(20.0)
        assert stats.bottleneck == "gpu"

    def test_a_capture_without_the_columns_still_reports_fps(self, tmp_path) -> None:
        """An older PresentMon loses the breakdown, not the frame rate."""
        capture = _capture(
            tmp_path,
            "cod26-cod.exe,10.0\ncod26-cod.exe,10.0\n",
            header="Application,MsBetweenPresents\n",
        )

        stats = PresentMonBenchmark().analyze_capture(capture)

        assert stats is not None
        assert stats.fps_avg == pytest.approx(100.0)
        assert stats.cpu_busy_ms == 0.0
        assert stats.bottleneck == "unknown"
        assert stats.present_mode == ""

    def test_cpu_busy_equal_to_frame_time_yields_unknown_from_a_real_csv(self, tmp_path) -> None:
        """PresentMon #222 as a fixture: every frame's MsCPUBusy equals its
        MsBetweenPresents while the GPU time sits a hair above. No side is
        established and no gated key appears."""
        capture = _capture(
            tmp_path,
            "cod26-cod.exe,17.18,17.18,17.33,0.0,,100.0\n"
            "cod26-cod.exe,17.18,17.18,17.33,0.0,,117.2\n"
            "cod26-cod.exe,17.18,17.18,17.33,0.0,,134.4\n",
        )

        stats = PresentMonBenchmark().analyze_capture(capture)

        assert stats is not None
        assert stats.bottleneck == "unknown"
        payload = stats.to_dict()
        assert "fps_gpu_bound" not in payload
        assert "fps_cpu_bound" not in payload
        assert "input_latency_ms" not in payload

    def test_unattributed_frames_are_skipped_rather_than_averaged_in(self, tmp_path) -> None:
        """PresentMon writes negative sentinels for frames it could not
        attribute. Averaging those in understates the cost that was really paid.
        """
        capture = _capture(
            tmp_path,
            "cod26-cod.exe,16.0,10.0,20.0,0.0,25.0,100.0\n"
            "cod26-cod.exe,16.0,-1.0,-1.0,0.0,-1.0,116.0\n"
            "cod26-cod.exe,16.0,10.0,20.0,0.0,25.0,132.0\n",
        )

        stats = PresentMonBenchmark().analyze_capture(capture)

        assert stats is not None
        assert stats.cpu_busy_ms == pytest.approx(10.0)
        assert stats.gpu_time_ms == pytest.approx(20.0)

    def test_empty_cells_do_not_become_zero(self, tmp_path) -> None:
        """An empty cell means "not reported". Read as 0.0 it would drag the
        average down and could flip the bottleneck verdict."""
        capture = _capture(
            tmp_path,
            "cod26-cod.exe,16.0,12.0,18.0,0.0,,100.0\ncod26-cod.exe,16.0,,18.0,0.0,,116.0\n",
        )

        stats = PresentMonBenchmark().analyze_capture(capture)

        assert stats is not None
        assert stats.cpu_busy_ms == pytest.approx(12.0)
        assert stats.input_latency_ms == 0.0

    def test_the_present_mode_is_the_path_most_frames_took(self, tmp_path) -> None:
        """A borderless game flips for most of the run and is composed for a few
        frames around an alt-tab; the run's mode is the majority, verbatim."""
        capture = _capture(
            tmp_path,
            "cod26-cod.exe,16.0,8.0,15.0,0.5,20.0,100.0,Hardware: Independent Flip\n"
            "cod26-cod.exe,16.0,8.0,15.0,0.5,20.0,116.0,Composed: Flip\n"
            "cod26-cod.exe,16.0,8.0,15.0,0.5,20.0,132.0,Hardware: Independent Flip\n",
            header=HEADER_WITH_MODE,
        )

        stats = PresentMonBenchmark().analyze_capture(capture)

        assert stats is not None
        assert stats.present_mode == "Hardware: Independent Flip"
        assert stats.to_dict()["present_mode"] == "Hardware: Independent Flip"

    def test_the_mpo_diagnostic_and_the_parser_read_the_same_column(self) -> None:
        from fpstune.diagnostics import mpo_effect

        assert mpo_effect.PRESENT_MODE_COLUMNS is PRESENT_MODE_COLUMNS

    def test_the_breakdown_reaches_the_serialised_form(self, tmp_path) -> None:
        """It has to survive to disk and to the API, or the UI cannot show it."""
        capture = _capture(tmp_path, "cod26-cod.exe,16.0,8.0,15.0,0.5,20.0,100.0\n")

        stats = PresentMonBenchmark().analyze_capture(capture)

        assert stats is not None
        payload = stats.to_dict()
        assert payload["cpu_busy_ms"] == 8.0
        assert payload["gpu_time_ms"] == 15.0
        assert payload["input_latency_ms"] == 20.0
        assert payload["bottleneck"] == "gpu"
        assert payload["fps_gpu_bound"] == payload["fps_avg"]


class TestTheStutterThreshold:
    def test_the_threshold_is_one_named_number(self) -> None:
        """2x, not CapFrameX's 2.5x — decided 2026-09-02 and recorded at the
        constant. A frame just above it is a stutter; one just below is not."""
        assert STUTTER_THRESHOLD_FACTOR == 2.0
        bench = PresentMonBenchmark()
        # The outlier lifts the average it is measured against: 99 frames at 10 ms
        # plus one at 25 ms average 10.15 ms, threshold 20.3 ms, one stutter; one
        # at 20 ms averages 10.1 ms, threshold 20.2 ms, no stutter.
        assert bench._calculate_stats([10.0] * 99 + [25.0], []).stutter_count == 1
        assert bench._calculate_stats([10.0] * 99 + [20.0], []).stutter_count == 0


class TestTheDownloadIsDiscoveredNotPinned:
    def test_no_pinned_release_url_survives_in_the_module(self) -> None:
        """The pinned v2.2.0 zip URL returned 404, so the benchmark could never
        install its own tool — and nothing reported that. The version and the
        packaging both moved; asking the API is the only thing that keeps
        working when they move again.
        """
        from fpstune.benchmark import presentmon

        assert not hasattr(presentmon, "PRESENTMON_RELEASE_URL")
        assert not hasattr(presentmon, "PRESENTMON_VERSION")
        assert "releases/latest" in presentmon.PRESENTMON_RELEASE_API

    def test_resolution_failure_is_not_an_exception(self, monkeypatch) -> None:
        """Offline is a normal state, not a crash. It leaves benchmarks
        unavailable, which is what the headroom logic already treats as
        'unmeasured'."""
        import urllib.request

        def refuse(*_args: object, **_kwargs: object) -> None:
            raise OSError("no network")

        monkeypatch.setattr(urllib.request, "urlopen", refuse)
        assert PresentMonBenchmark().resolve_download() is None
