"""The in-game frame-rate probe, tested against what actually happened.

Run against a live MW4 on 2026-08-25, at the user's request ("I am opening a
game, check whether in-game fps detection works"). It did not, and it failed in
three ways that stacked:

1. **The flags were PresentMon 1.x.** `--no_top` does not exist in 2.5.1, which
   is the version fpstune downloads. It is not ignored — PresentMon prints
   `error: unrecognized option '--no_top'` and exits without recording anything.
2. **The capture was killed the moment it started.** `probe_running_game` called
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
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpstune.benchmark.presentmon import PresentMonBenchmark
from fpstune.settings.performance_headroom import (
    explain_capture_failure,
    probe_running_game,
)

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
        return calls

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
    def test_the_probe_waits_instead_of_killing_what_it_just_started(self, monkeypatch) -> None:
        """The 0.6-second ten-second capture, pinned.

        `wait_for_capture` must be called between starting and stopping, or the
        recording is terminated before PresentMon has written a row.
        """
        order: list[str] = []

        class FakeCapture:
            last_error = ""

            def is_installed(self) -> bool:
                return True

            def start_capture(self, **_kwargs) -> bool:
                order.append("start")
                return True

            def wait_for_capture(self, timeout: float) -> bool:
                order.append(f"wait:{timeout}")
                return True

            def stop_capture(self) -> Path | None:
                order.append("stop")
                return None

            def analyze_capture(self, _path):  # pragma: no cover - never reached
                return None

        monkeypatch.setattr(
            "fpstune.benchmark.presentmon.PresentMonBenchmark", lambda *_a, **_k: FakeCapture()
        )
        probe_running_game("mw4", 297, duration_seconds=10, now=1000.0)

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

    def test_the_probe_passes_the_reason_up(self, monkeypatch) -> None:
        class RefusingCapture:
            last_error = ACCESS_DENIED

            def is_installed(self) -> bool:
                return True

            def start_capture(self, **_kwargs) -> bool:
                return True

            def wait_for_capture(self, _timeout: float) -> bool:
                return True

            def stop_capture(self) -> Path | None:
                return None

            def analyze_capture(self, _path):  # pragma: no cover - never reached
                return None

        monkeypatch.setattr(
            "fpstune.benchmark.presentmon.PresentMonBenchmark",
            lambda *_a, **_k: RefusingCapture(),
        )

        recorded, reason = probe_running_game("mw4", 297, duration_seconds=1, now=1000.0)

        assert recorded is False
        assert "administrator" in reason.lower()


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
