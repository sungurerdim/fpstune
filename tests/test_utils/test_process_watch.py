"""A watched run ends on silence, never on duration.

Fixed ceilings killed work that was going fine: a 30 s restore point mid-snapshot,
a 60 s Windows Update cache cleanup mid-delete. These tests run real child
processes (the interpreter running this suite) with an injected activity probe,
so the stall logic is exercised on any host; the Job Object itself is covered by
the Windows contract test.
"""

from __future__ import annotations

import sys
from dataclasses import replace

from fpstune.utils.process_watch import (
    CHANGE,
    QUERY,
    SERVICING,
    StallPolicy,
    describe_stall,
    run_watched,
)
from fpstune.utils.winapi.job import TreeActivity

FAST = StallPolicy("test", stall_s=0.6, sample_s=0.05)


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


class _Probe:
    """A tree whose counters the test scripts; records whether it was stopped."""

    def __init__(self, process, *, io_per_sample: int = 0, cpu_per_sample: float = 0.0):
        self._process = process
        self._io = 0
        self._cpu = 0.0
        self._io_step = io_per_sample
        self._cpu_step = cpu_per_sample
        self.terminated = False

    def activity(self) -> TreeActivity | None:
        self._io += self._io_step
        self._cpu += self._cpu_step
        return TreeActivity(self._cpu, self._io, 1)

    def terminate(self) -> None:
        self.terminated = True
        self._process.kill()

    def close(self) -> None:
        return None


def _factory(store: list[_Probe], **kwargs):
    def make(process):
        probe = _Probe(process, **kwargs)
        store.append(probe)
        return probe

    return make


SILENT_FOR_3S = "import time; time.sleep(3)"


class TestASlowRunThatKeepsMovingIsNeverCut:
    def test_steady_output_outlives_the_stall_window(self) -> None:
        code = "import time\nfor i in range(12):\n    print(i, flush=True); time.sleep(0.15)"
        probes: list[_Probe] = []
        result = run_watched(_py(code), FAST, probe_factory=_factory(probes))
        assert result.ok, result.reason
        assert result.stdout.split() == [str(i) for i in range(12)]
        assert not probes[0].terminated

    def test_a_silent_run_moving_bytes_is_not_stuck(self) -> None:
        """Remove-Item over 15 GB prints nothing and writes the whole time."""
        probes: list[_Probe] = []
        result = run_watched(
            _py("import time; time.sleep(1.5)"),
            FAST,
            probe_factory=_factory(probes, io_per_sample=4096),
        )
        assert result.ok, result.reason

    def test_a_silent_run_doing_cpu_work_is_not_stuck(self) -> None:
        probes: list[_Probe] = []
        result = run_watched(
            _py("import time; time.sleep(1.5)"),
            FAST,
            probe_factory=_factory(probes, cpu_per_sample=FAST.sample_s),
        )
        assert result.ok, result.reason


class TestAStuckRunIsNamedAndHandled:
    def test_a_stall_is_logged_for_every_caller(self, caplog) -> None:
        """Callers that turn a stall into an empty reading must not hide it."""
        with caplog.at_level("WARNING", logger="fpstune.utils.process_watch"):
            run_watched(_py(SILENT_FOR_3S), FAST, probe_factory=_factory([]))
        assert any("stopped: no progress for" in r.getMessage() for r in caplog.records)

    def test_silence_past_the_window_is_a_timeout_and_the_tree_is_stopped(self) -> None:
        probes: list[_Probe] = []
        result = run_watched(_py(SILENT_FOR_3S), FAST, probe_factory=_factory(probes))
        assert result.timed_out and not result.ok
        assert not result.left_running
        assert result.reason.startswith("no progress for")
        assert probes[0].terminated

    def test_a_polling_loop_below_the_cpu_floor_is_still_stuck(self) -> None:
        """A script spinning on a lock that never frees must not run forever."""
        probes: list[_Probe] = []
        trickle = FAST.cpu_floor * FAST.sample_s / 4
        result = run_watched(
            _py(SILENT_FOR_3S), FAST, probe_factory=_factory(probes, cpu_per_sample=trickle)
        )
        assert result.timed_out

    def test_servicing_is_reported_but_left_to_finish(self) -> None:
        probes: list[_Probe] = []
        policy = replace(FAST, on_stall="leave")
        result = run_watched(_py(SILENT_FOR_3S), policy, probe_factory=_factory(probes))
        assert result.timed_out and result.left_running
        assert not probes[0].terminated
        assert result.reason.endswith("(left running)")


class TestOrdinaryOutcomes:
    def test_exit_code_and_stderr_come_back(self) -> None:
        code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"
        result = run_watched(_py(code), FAST, probe_factory=_factory([]))
        assert (result.returncode, result.stdout.strip(), result.stderr.strip()) == (
            3,
            "out",
            "err",
        )
        assert not result.ok and not result.timed_out

    def test_output_is_handed_over_while_running(self) -> None:
        seen: list[str] = []
        # Raw UTF-8 bytes: on Windows a piped child's print() encodes with the
        # system code page, which cannot write these letters at all.
        run_watched(
            _py("import sys; sys.stdout.buffer.write('ğüşıöç'.encode()); sys.stdout.flush()"),
            FAST,
            on_text=seen.append,
            probe_factory=_factory([]),
        )
        assert "".join(seen).strip() == "ğüşıöç"

    def test_merged_stderr_keeps_terminal_order(self) -> None:
        code = "import sys\nprint('a', flush=True)\nprint('b', file=sys.stderr, flush=True)"
        result = run_watched(_py(code), FAST, merge_stderr=True, probe_factory=_factory([]))
        assert result.stdout.split() == ["a", "b"]


class TestNamedPolicies:
    def test_every_policy_waits_minutes_or_a_query_minute(self) -> None:
        assert QUERY.stall_s >= 60
        assert CHANGE.stall_s >= 300
        assert SERVICING.on_stall == "leave"

    def test_the_stall_sentence_is_one_wording(self) -> None:
        assert describe_stall(CHANGE) == "no progress for 5 min"
        assert describe_stall(SERVICING) == "no progress for 15 min (left running)"
        assert describe_stall(StallPolicy("x", stall_s=90)) == "no progress for 90 s"
