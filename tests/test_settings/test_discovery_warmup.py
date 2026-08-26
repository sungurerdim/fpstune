"""Discovery asks the machine seven questions, and none waits on another.

Measured before this landed: 3.85 s of subprocess time inside a 3.86 s
discovery — strictly back to back, and almost all of it PowerShell startup
rather than work. Which adapters exist, what queue counts their driver
publishes, which one carries the default route, what the GPU is, what the
monitors are, which Windows build this is: six independent questions asked one
after another.

    discovery   3.86s  ->  1.65s

The concurrency is the kind of thing that reverts silently. Nothing breaks if
the warm-up stops running or the probes stop memoising — every value is still
correct, every test still passes, and discovery just quietly costs twice as
much again. So these assert the structure rather than a duration: a timing
assertion would be flaky on a loaded machine and would tell nobody why it broke.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

from fpstune.settings.discovery.probes import HardwareProbes


class TestProbesAnswerOnce:
    """Warming concurrently only helps if the second ask is free."""

    def test_a_repeated_probe_does_not_ask_the_machine_again(self) -> None:
        probes = HardwareProbes()
        calls = []

        def counted() -> str:
            calls.append(1)
            return "answer"

        assert probes.probe_once("k", counted) == "answer"
        assert probes.probe_once("k", counted) == "answer"
        assert len(calls) == 1

    def test_different_questions_keep_their_own_answers(self) -> None:
        probes = HardwareProbes()

        assert probes.probe_once("a", lambda: 1) == 1
        assert probes.probe_once("b", lambda: 2) == 2
        assert probes.probe_once("a", lambda: 99) == 1

    def test_two_threads_asking_at_once_still_ask_the_machine_once(self) -> None:
        """The check-then-compute race the per-scan batch cache had to fix.

        The warm-up runs these in parallel, so this is the actual arrangement,
        not a hypothetical one.
        """
        probes = HardwareProbes()
        calls: list[int] = []
        start = threading.Barrier(4)

        def slow() -> str:
            calls.append(1)
            time.sleep(0.05)
            return "answer"

        def ask() -> None:
            start.wait(timeout=5)
            probes.probe_once("shared", slow)

        threads = [threading.Thread(target=ask) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(calls) == 1, f"{len(calls)} threads each ran the probe the cache exists to avoid"

    def test_one_slow_question_does_not_hold_up_a_different_one(self) -> None:
        """A single lock across all probes would serialise exactly what the
        warm-up exists to overlap — the whole cost being removed.

        Arranged with events rather than raced sleeps: the slow probe is
        *held* inside its computation until the quick one has finished, so
        under per-key locks the quick probe completes immediately, while under
        one shared lock it can never complete before the slow one is released
        — which only happens after the assertion. The timeouts are liveness
        bounds, not a race: no scheduler stall can flip the outcome, only a
        genuine serialisation can.
        """
        probes = HardwareProbes()
        slow_entered = threading.Event()
        release_slow = threading.Event()
        quick_done = threading.Event()

        def slow() -> str:
            slow_entered.set()
            release_slow.wait(timeout=10)
            return "slow"

        def ask_quick() -> None:
            probes.probe_once("quick", lambda: "quick")
            quick_done.set()

        slow_thread = threading.Thread(target=lambda: probes.probe_once("slow", slow))
        quick_thread = threading.Thread(target=ask_quick)
        try:
            slow_thread.start()
            assert slow_entered.wait(timeout=5), "the slow probe never started computing"

            # The slow probe now provably holds its per-key lock.
            quick_thread.start()
            assert quick_done.wait(timeout=5), (
                "the quick probe waited for the slow one, so the probes are serialised"
            )
        finally:
            release_slow.set()
            slow_thread.join(timeout=5)
            quick_thread.join(timeout=5)

        assert probes.probe_once("quick", lambda: "stale") == "quick"
        assert probes.probe_once("slow", lambda: "stale") == "slow"


class TestTheWarmUpRunsThemTogether:
    def test_every_independent_probe_is_warmed(self) -> None:
        """A probe left out of the list stays on the sequential path.

        Named individually rather than counted, so adding a seventh probe and
        forgetting to warm it is a failure rather than a silent regression.
        """
        probes = HardwareProbes()
        asked: list[str] = []

        with (
            patch.object(probes, "active_adapters", side_effect=lambda: asked.append("adapters")),
            patch.object(probes, "rss_queue_options", side_effect=lambda: asked.append("rss")),
            patch.object(
                probes,
                "default_route_interface_index",
                side_effect=lambda: asked.append("route"),
            ),
            patch("fpstune.utils.detect.get_gpu_info", side_effect=lambda: asked.append("gpu")),
            patch(
                "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
                side_effect=lambda: asked.append("monitors"),
            ),
            patch(
                "fpstune.utils.hardware_manager.hardware_manager.detect_os",
                side_effect=lambda: asked.append("os"),
            ),
        ):
            probes.warm()

        assert sorted(asked) == ["adapters", "gpu", "monitors", "os", "route", "rss"]

    def test_they_overlap_rather_than_queue(self) -> None:
        """The point of the warm-up, asserted by arrangement rather than clock.

        Each probe blocks on a barrier that only releases once all six have
        arrived. If any of them ran after another finished, the barrier would
        never fill and this would time out.
        """
        probes = HardwareProbes()
        gate = threading.Barrier(6, timeout=10)

        def arrive() -> str:
            gate.wait()
            return "here"

        with (
            patch.object(probes, "active_adapters", side_effect=arrive),
            patch.object(probes, "rss_queue_options", side_effect=arrive),
            patch.object(probes, "default_route_interface_index", side_effect=arrive),
            patch("fpstune.utils.detect.get_gpu_info", side_effect=arrive),
            patch(
                "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
                side_effect=arrive,
            ),
            patch("fpstune.utils.hardware_manager.hardware_manager.detect_os", side_effect=arrive),
        ):
            probes.warm()

        assert gate.n_waiting == 0
        assert not gate.broken, "the probes did not all run at once; they are back to sequential"

    def test_a_failing_probe_does_not_break_discovery(self) -> None:
        """Each probe already degrades on its own. A warm-up must never be the
        thing that turns a recoverable failure into no settings at all."""
        probes = HardwareProbes()

        with patch.object(probes, "active_adapters", side_effect=OSError("no adapters")):
            probes.warm()  # must not raise
