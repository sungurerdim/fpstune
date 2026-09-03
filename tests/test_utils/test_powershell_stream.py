"""Live output arrives while the command runs, shaped the way a terminal shows it.

A repair that prints nothing for thirty minutes is indistinguishable from one
that has hung, which is the whole reason this runner exists. Two things have to
hold for the output to be worth showing: it has to arrive during the run, and a
progress bar that redraws itself has to read as one line rather than as three
hundred.
"""

from __future__ import annotations

import sys
import time

import pytest

from fpstune.utils.powershell import _LineSplitter, run_powershell_stream

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="the PowerShell runner is Windows-only"
)


class TestLineSplitter:
    """The CR/LF rules, against the shapes DISM and SFC actually print."""

    def _collect(self, *chunks: str) -> list[tuple[str, bool]]:
        seen: list[tuple[str, bool]] = []
        splitter = _LineSplitter(lambda text, replaces: seen.append((text, replaces)))
        for chunk in chunks:
            splitter.feed(chunk)
        splitter.close()
        return seen

    def test_a_line_feed_ends_a_line(self) -> None:
        assert self._collect("first\nsecond\n") == [("first", False), ("second", False)]

    def test_crlf_is_one_ordinary_line_ending(self) -> None:
        """Windows tools end real lines with CRLF; that is not a redraw."""
        assert self._collect("first\r\nsecond\r\n") == [("first", False), ("second", False)]

    def test_a_bare_carriage_return_marks_a_redraw(self) -> None:
        """DISM returns the carriage and prints the next bar over the last one."""
        assert self._collect("[=   10% ]\r[==  20% ]\r") == [
            ("[=   10% ]", True),
            ("[==  20% ]", True),
        ]

    def test_a_line_ending_split_across_chunks_stays_one_line(self) -> None:
        """The CR and its LF can arrive in different reads; that is still CRLF."""
        assert self._collect("done\r", "\nnext\n") == [("done", False), ("next", False)]

    def test_an_unterminated_tail_is_flushed_at_the_end(self) -> None:
        assert self._collect("no newline here") == [("no newline here", False)]

    def test_the_carriage_return_before_a_bar_carries_nothing(self) -> None:
        """A tool that writes CR *then* the bar must not produce empty rows."""
        assert self._collect("\r[=   10% ]\r\r[==  20% ]\r") == [
            ("[=   10% ]", True),
            ("[==  20% ]", True),
        ]


def test_output_arrives_while_the_command_is_still_running() -> None:
    """Not "after it finishes": the first line must land before the last one does."""
    seen: list[tuple[float, str]] = []
    start = time.monotonic()

    ok, output = run_powershell_stream(
        'foreach ($i in 1..3) { Write-Output "step $i"; Start-Sleep -Milliseconds 700 }',
        lambda text, _replaces: seen.append((time.monotonic() - start, text)),
        timeout=30,
    )

    assert ok is True
    assert [text for _at, text in seen] == ["step 1", "step 2", "step 3"]
    first_at = seen[0][0]
    last_at = seen[-1][0]
    assert last_at - first_at > 0.5, (
        f"every line arrived at once ({first_at:.2f}s..{last_at:.2f}s) — the output "
        "was buffered until the command finished"
    )
    assert output.splitlines() == ["step 1", "step 2", "step 3"]


def test_a_redrawn_bar_collapses_into_one_line_of_output() -> None:
    """The captured output holds the last bar, not one row per redraw."""
    seen: list[tuple[str, bool]] = []

    ok, output = run_powershell_stream(
        'foreach ($p in 10,20,30) { [Console]::Out.Write("[ $p% ]`r") }; '
        "Write-Output 'The operation completed successfully.'",
        lambda text, replaces: seen.append((text, replaces)),
        timeout=30,
    )

    assert ok is True
    assert [text for text, replaces in seen if replaces] == ["[ 10% ]", "[ 20% ]", "[ 30% ]"]
    # Three redraws, one line: the caller that honours `replaces` shows a bar,
    # not a wall.
    assert output.splitlines() == ["[ 30% ]", "The operation completed successfully."]


def test_the_timeout_is_honoured() -> None:
    start = time.monotonic()

    ok, output = run_powershell_stream(
        "Write-Output 'working'; Start-Sleep -Seconds 30",
        lambda _text, _replaces: None,
        timeout=3,
    )

    elapsed = time.monotonic() - start
    assert ok is False
    assert "timed out" in output
    assert elapsed < 15, f"returned after {elapsed:.1f}s for a 3 s timeout"


def test_a_failing_command_reports_its_output_as_the_error() -> None:
    ok, output = run_powershell_stream(
        "Write-Output 'nothing to do here'; exit 3",
        lambda _text, _replaces: None,
        timeout=30,
    )

    assert ok is False
    assert "nothing to do here" in output
