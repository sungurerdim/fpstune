"""Tests for reading where a frame's time actually went.

A frame rate on its own is a number with no cause attached: 57 fps says nothing
about whether lowering a shadow setting would help. PresentMon 2.x reports the
CPU and GPU cost of every frame, and until now the parser read only the interval
between presents and threw the rest away.

The measurement that motivated this, taken from a live MW4 session: CPU 17.18 ms
against GPU 17.33 ms. The in-game overlay had suggested a GPU bottleneck; the
capture says both sides are saturated, which means relieving either one alone
moves the frame rate barely at all.
"""

from __future__ import annotations

import pytest

from fpstune.benchmark.presentmon import FrameTimeStats, PresentMonBenchmark

# Column names as PresentMon 2.5.1 writes them, trimmed to what is read.
HEADER = (
    "Application,MsBetweenPresents,MsCPUBusy,MsGPUTime,MsGPUWait,"
    "MsAllInputToPhotonLatency,TimeInMs\n"
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

    def test_two_saturated_sides_are_reported_as_both(self) -> None:
        """The measured case. Calling this GPU-bound because the GPU is a hair
        higher would send a user to change settings that cannot help them."""
        stats = FrameTimeStats(cpu_busy_ms=17.18, gpu_time_ms=17.33)
        assert stats.bottleneck == "both"

    @pytest.mark.parametrize(
        ("cpu", "gpu", "expected"),
        [
            (10.0, 10.9, "both"),  # inside the band
            (10.0, 11.1, "gpu"),  # just outside it
            (10.9, 10.0, "both"),
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
