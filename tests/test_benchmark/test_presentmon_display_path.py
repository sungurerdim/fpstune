"""The cadence the panel showed, and the flags that must never be guessed at.

`MsBetweenPresents` is what the *application* submitted. A game running at 300
fps on a 60 Hz panel submits a frame every 3.3 ms and the screen changes every
16.7 ms, and until now fpstune only read the first of those — the number that
flatters the machine and that no player sees.

Two failure modes are pinned here.

*A flag that does not exist is fatal, not ignored.* Measured against the
installed PresentMon 2.5.1: `--not_a_real_flag` produces `error: unrecognized
option` and the process exits before recording a frame — which is exactly how
`--no_top` once turned every capture into an empty file diagnosed as "the game
was in a menu". So an optional flag is passed only when the build's own `--help`
lists it.

*A column that did not arrive is not a zero.* The display columns are renamed
between PresentMon majors and gated on prerequisites that live outside this
machine (a game instrumented for PC Latency events, an LMT or PCAT device), so
what arrived is read from the CSV header, and what did not says why.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpstune.benchmark.presentmon import (
    OPTIONAL_TRACKING_FLAGS,
    PresentMonBenchmark,
)

_HELP_2_5_1 = """PresentMon 2.5.1

Output Options:
  --output_file path            Write CSV output to the specified path.
  --no_console_stats            Do not display active swap chains.

Beta Options:
  --track_hw_measurements       Tracks HW-measured latency and/or power data
                                coming from a LMT and/or PCAT device.
  --track_pc_latency            Track app timines for each displayed frame;
                                requires application instrumentation using PC
                                Latency events.
"""

_HELP_WITHOUT_BETA = """PresentMon 1.9.0

Output Options:
  --output_file path            Write CSV output to the specified path.
"""


def _bench(tmp_path: Path) -> PresentMonBenchmark:
    bench = PresentMonBenchmark(data_dir=tmp_path)
    bench.presentmon_path.parent.mkdir(parents=True, exist_ok=True)
    bench.presentmon_path.write_bytes(b"stub")
    return bench


def _with_help(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(_cmd, **_kwargs):
        return subprocess.CompletedProcess(_cmd, 0, stdout=text.encode(), stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)


def _capture(tmp_path: Path, header: str, rows: list[str]) -> Path:
    path = tmp_path / "capture.csv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


class TestOnlyFlagsTheBuildAdmitsTo:
    def test_a_build_that_lists_them_gets_them(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bench = _bench(tmp_path)
        _with_help(_HELP_2_5_1, monkeypatch)

        assert bench.supported_tracking_flags() == list(OPTIONAL_TRACKING_FLAGS)
        assert bench.tracking_flag_gaps() == {}

    def test_a_build_without_them_is_never_handed_them(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unrecognized option makes PresentMon exit before recording."""
        bench = _bench(tmp_path)
        _with_help(_HELP_WITHOUT_BETA, monkeypatch)

        assert bench.supported_tracking_flags() == []
        assert set(bench.tracking_flag_gaps()) == set(OPTIONAL_TRACKING_FLAGS)

    def test_the_capture_command_carries_the_flags_the_build_has(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bench = _bench(tmp_path)
        monkeypatch.setattr(bench, "supported_tracking_flags", lambda: ["--track_pc_latency"])
        started: list[list[str]] = []

        def fake_popen(cmd, **_kwargs):
            started.append(list(cmd))
            process = MagicMock()
            process.poll.return_value = None
            return process

        monkeypatch.setattr(subprocess, "Popen", fake_popen)
        bench.start_capture(output_name="probe")

        # The capture, not the `--help` probe that `subprocess.run` also
        # starts through Popen on the way to it.
        capture = next(cmd for cmd in started if "--output_file" in cmd)
        assert "--track_pc_latency" in capture

    def _capture_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, help_text: str
    ) -> list[str]:
        bench = _bench(tmp_path)
        _with_help(help_text, monkeypatch)
        started: list[list[str]] = []

        def fake_popen(cmd, **_kwargs):
            started.append(list(cmd))
            process = MagicMock()
            process.poll.return_value = None
            return process

        monkeypatch.setattr(subprocess, "Popen", fake_popen)
        bench.start_capture(process_name="game.exe", output_name="probe")
        return started[0]

    def test_a_leftover_trace_session_is_taken_over(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A capture terminated mid-run leaves its ETW session alive, and the
        next start is refused: `error: a trace session named "PresentMon" is
        already running. Use --stop_existing_session ...` — measured 2026-09-11
        on PresentMon 2.5.1, second capture after `stop_capture()` had
        terminated the first. Every capture after the first would fail."""
        help_text = _HELP_2_5_1 + "  --stop_existing_session       Stop the leftover session.\n"

        assert "--stop_existing_session" in self._capture_command(tmp_path, monkeypatch, help_text)

    def test_a_build_without_session_takeover_is_not_handed_a_fatal_option(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert "--stop_existing_session" not in self._capture_command(
            tmp_path, monkeypatch, _HELP_WITHOUT_BETA
        )

    def test_a_help_probe_that_fails_never_breaks_the_capture(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The worst an unreadable option list may cost is the optional flags."""
        bench = _bench(tmp_path)

        def explode(*_args, **_kwargs):
            raise RuntimeError("the help probe fell over")

        monkeypatch.setattr(subprocess, "run", explode)

        assert bench.supported_tracking_flags() == []

    def test_the_option_list_is_read_once_per_session(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bench = _bench(tmp_path)
        calls: list[int] = []

        def fake_run(_cmd, **_kwargs):
            calls.append(1)
            return subprocess.CompletedProcess(_cmd, 0, stdout=_HELP_2_5_1.encode(), stderr=b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        bench.supported_flags()
        bench.supported_flags()

        assert len(calls) == 1


class TestWhatReachedTheScreen:
    def test_the_display_cadence_is_read_from_a_two_x_capture(self, tmp_path: Path) -> None:
        """300 fps submitted to a 60 Hz panel is 16.7 ms between display changes."""
        capture = _capture(
            tmp_path,
            "FrameTime,DisplayedTime,DisplayLatency,AnimationError",
            ["3.3,16.7,20.1,-1.2", "3.3,16.7,19.9,1.4"],
        )

        stats = PresentMonBenchmark(data_dir=tmp_path).analyze_capture(capture)

        assert stats is not None
        assert stats.display_change_ms == pytest.approx(16.7)
        assert stats.to_dict()["fps_displayed"] == pytest.approx(59.88, abs=0.05)

    def test_the_one_x_spelling_reads_the_same_quantity(self, tmp_path: Path) -> None:
        capture = _capture(
            tmp_path,
            "MsBetweenPresents,MsBetweenDisplayChange,MsUntilDisplayed,MsAnimationError",
            ["3.3,16.7,20.1,0.8", "3.3,16.7,19.9,0.6"],
        )

        stats = PresentMonBenchmark(data_dir=tmp_path).analyze_capture(capture)

        assert stats is not None
        assert stats.display_change_ms == pytest.approx(16.7)
        assert stats.until_displayed_ms == pytest.approx(20.0)

    def test_animation_error_keeps_its_size_and_drops_its_sign(self, tmp_path: Path) -> None:
        """A frame shown early is as wrong as one shown late.

        Read the way the cost columns are read — negatives discarded — the two
        errors here would cancel to 0.1 ms and report a machine drifting half a
        frame either way as almost perfectly paced.
        """
        capture = _capture(
            tmp_path,
            "FrameTime,DisplayedTime,AnimationError",
            ["3.3,16.7,-4.0", "3.3,16.7,4.0"],
        )

        stats = PresentMonBenchmark(data_dir=tmp_path).analyze_capture(capture)

        assert stats is not None
        assert stats.animation_error_ms == pytest.approx(4.0)


class TestAMissingColumnSaysWhy:
    def test_a_capture_without_the_display_columns_reports_reasons(self, tmp_path: Path) -> None:
        capture = _capture(tmp_path, "MsBetweenPresents", ["16.7", "16.6"])

        stats = PresentMonBenchmark(data_dir=tmp_path).analyze_capture(capture)

        assert stats is not None
        payload = stats.to_dict()
        assert "display_change_ms" not in payload
        assert "fps_displayed" not in payload
        for key in ("display_change", "until_displayed", "animation_error"):
            assert payload["unmeasured"][key]

    def test_a_column_that_arrived_empty_is_named_as_such(self, tmp_path: Path) -> None:
        """ "The column was there and said nothing" is a different fix."""
        capture = _capture(tmp_path, "MsBetweenPresents,DisplayedTime", ["16.7,NA", "16.6,NA"])

        stats = PresentMonBenchmark(data_dir=tmp_path).analyze_capture(capture)

        assert stats is not None
        assert "DisplayedTime" in stats.unmeasured["display_change"]

    def test_a_flag_the_build_lacks_is_listed_beside_the_columns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bench = _bench(tmp_path)
        _with_help(_HELP_WITHOUT_BETA, monkeypatch)
        capture = _capture(tmp_path, "MsBetweenPresents", ["16.7", "16.6"])

        stats = bench.analyze_capture(capture)

        assert stats is not None
        assert "--track_pc_latency" in stats.unmeasured

    def test_a_complete_capture_reports_no_gaps_at_all(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bench = _bench(tmp_path)
        _with_help(_HELP_2_5_1, monkeypatch)
        capture = _capture(
            tmp_path,
            "FrameTime,DisplayedTime,DisplayLatency,AnimationError",
            ["3.3,16.7,20.1,0.4", "3.3,16.7,19.9,0.6"],
        )

        stats = bench.analyze_capture(capture)

        assert stats is not None
        assert stats.unmeasured == {}
        assert "unmeasured" not in stats.to_dict()
