"""The frame capture, tested against what actually happened.

Run against a live MW4 on 2026-08-25, at the user's request ("I am opening a
game, check whether in-game fps detection works"). It did not, and it failed in
three ways that stacked:

1. **The flags were PresentMon 1.x.** `--no_top` does not exist in 2.5.1, which
   is the version fpstune downloads. It is not ignored — PresentMon prints
   `error: unrecognized option '--no_top'` and exits without recording anything.
2. **The capture was killed the moment it started.** The caller called
   `start_capture` (which only spawns the process) and then `stop_capture`
   (which terminates it) with nothing in between. A ten-second probe returned in
   0.6 s.
3. **The failure was diagnosed wrongly.** With an empty CSV, the product reported
   "the capture produced no frames — it may have been in a menu or minimised".
   PresentMon had in fact said, on stderr, that it could not open a trace session
   without administrator rights. A fixable problem was reported as an unfixable
   one, and the stderr was discarded unread.

The third is the one worth the most: 1 and 2 are bugs, 3 is the product telling
the user something untrue about their own machine.

The caller that made mistake 2 is gone — the in-game probe was retired on
2026-09-11 in favour of the fixed scene — so that contract is held here against
`gpu_scene`, which is now the one thing that drives a capture. The mistake is a
property of *any* caller of this tool, which is why it is pinned beside the tool
rather than left to whichever module happens to call it this year.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpstune.benchmark import gpu_scene
from fpstune.benchmark.gpu_scene import GpuSceneBench
from fpstune.benchmark.presentmon import PresentMonBenchmark
from fpstune.settings.performance_headroom import explain_capture_failure

ACCESS_DENIED = (
    "error: failed to start trace session: access denied.\n"
    "       PresentMon requires either administrative privileges or to be run by a user\n"
    '       in the "Performance Log Users" user group.'
)


class TestTheCommandLine:
    @pytest.fixture
    def spawned(self, tmp_path, monkeypatch) -> list[list[str]]:
        calls: list[list[str]] = []

        def fake_popen(cmd, **_kwargs):
            calls.append(list(cmd))
            process = MagicMock()
            process.poll.return_value = 0
            process.communicate.return_value = (b"", b"")
            return process

        monkeypatch.setattr(subprocess, "Popen", fake_popen)
        bench = PresentMonBenchmark(data_dir=tmp_path)
        bench.presentmon_path.parent.mkdir(parents=True, exist_ok=True)
        bench.presentmon_path.write_bytes(b"stub")
        bench.start_capture(process_name="game.exe", output_name="probe", duration_seconds=10)
        # The capture, not whatever else the module ran the executable for. It
        # also asks `--help` once per session to find out which optional flags
        # this build accepts, and a fixture keyed to "the first process started"
        # would silently start testing that instead.
        return [cmd for cmd in calls if "--output_file" in cmd]

    def test_no_flag_from_presentmon_1x_survives(self, spawned) -> None:
        """`--no_top` is rejected outright by 2.x, so the capture records nothing."""
        assert "--no_top" not in spawned[0]

    def test_console_stats_are_suppressed_the_2x_way(self, spawned) -> None:
        assert "--no_console_stats" in spawned[0]

    def test_a_timed_capture_is_told_to_exit_when_it_is_done(self, spawned) -> None:
        """`--timed` stops recording; only `--terminate_after_timed` stops the
        process. Without it a caller waiting for the end waits for the timeout."""
        cmd = spawned[0]
        assert "--timed" in cmd
        assert "--terminate_after_timed" in cmd

    def test_the_target_process_is_named(self, spawned) -> None:
        cmd = spawned[0]
        assert cmd[cmd.index("--process_name") + 1] == "game.exe"


class TestTheCaptureIsGivenTimeToRun:
    """The 0.6-second ten-second capture, pinned against today's only caller.

    `wait_for_capture` has to be called between starting and stopping, or the
    recording is terminated before PresentMon has written a row. `start_capture`
    spawns the process and returns; `stop_capture` terminates it. Nothing in
    either signature says so, which is exactly why this is a test and not a
    comment.
    """

    def test_the_scene_waits_instead_of_killing_what_it_just_started(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        order: list[str] = []
        log = tmp_path / "log.html"

        class FakeCapture:
            last_error = ""

            def start_capture(self, **_kwargs: object) -> bool:
                order.append("start")
                return True

            def wait_for_capture(self, timeout: float) -> bool:
                order.append(f"wait:{timeout}")
                return True

            def stop_capture(self) -> Path | None:
                order.append("stop")
                return None

            def terminate_child(self) -> None:
                pass

        def fake_spawn(_args: list[str], _cwd: Path) -> MagicMock:
            # The engine announces itself in its own log; the bench polls for
            # that line and starts recording afterwards.
            log.write_text(f"<p>{gpu_scene.RUNNING_MARKER}</p>", encoding="utf-8")
            process = MagicMock()
            process.poll.return_value = None
            process.pid = 4242
            return process

        monkeypatch.setattr(gpu_scene, "_spawn_engine", fake_spawn)
        monkeypatch.setattr(gpu_scene, "_kill_tree", lambda _pid: None)

        bench = GpuSceneBench(
            data_dir=tmp_path,
            seconds_per_sample=10.0,
            settle_seconds=0.0,
            poll_seconds=0.0,
            presentmon=FakeCapture(),  # type: ignore[arg-type]
            log_path=log,
        )
        bench._measure(2560, 1440, 1, 0.0)

        assert order[0] == "start"
        assert order[1].startswith("wait:"), "the capture was stopped before it could record"
        assert order[2] == "stop"
        # The wait covers the capture's own duration plus PresentMon's startup.
        assert float(order[1].split(":")[1]) >= 10


class TestTheFailureIsDiagnosedFromWhatPresentMonSaid:
    def test_access_denied_is_reported_as_needing_elevation(self) -> None:
        reason = explain_capture_failure(ACCESS_DENIED)

        assert "administrator" in reason.lower()
        # And never the guess that was printed over it.
        assert "menu" not in reason.lower()

    def test_a_rejected_flag_is_named_as_our_bug_not_the_machine_s(self) -> None:
        reason = explain_capture_failure("error: unrecognized option '--no_top'.")

        assert "fpstune" in reason.lower()
        assert "not a problem with the game" in reason.lower()

    def test_silence_from_presentmon_produces_no_invented_reason(self) -> None:
        """An empty capture with no stderr genuinely might have been a menu; the
        caller's fallback is right there and must not be pre-empted."""
        assert explain_capture_failure("") == ""
        assert explain_capture_failure("some unrelated chatter") == ""

    # That the caller passes this reason up rather than printing its own guess is
    # pinned where the caller lives:
    # `test_performance_headroom.py::TestMeasuringOnDemand
    # ::test_presentmons_own_refusal_is_translated_into_something_fixable`.


class TestStderrIsRead:
    def test_stop_capture_keeps_what_presentmon_said(self, tmp_path, monkeypatch) -> None:
        """Discarding stderr is what left the product guessing."""
        process = MagicMock()
        process.poll.return_value = 0
        process.communicate.return_value = (b"", ACCESS_DENIED.encode())
        monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: process)

        bench = PresentMonBenchmark(data_dir=tmp_path)
        bench.presentmon_path.parent.mkdir(parents=True, exist_ok=True)
        bench.presentmon_path.write_bytes(b"stub")
        bench.start_capture(process_name="game.exe", output_name="probe", duration_seconds=1)
        bench.stop_capture()

        assert "access denied" in bench.last_error.lower()
