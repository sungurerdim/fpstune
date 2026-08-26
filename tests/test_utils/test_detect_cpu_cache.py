"""Regression tests: CPU detection is session-cached (PERF-17, PERF-18).

``get_cpu_info()`` and ``get_cpu_detailed_info()`` used to spawn a PowerShell
process on every call while being reached from async API routes. C7 forbids a
subprocess per request for session-stable data, so each detector must run its
subprocess at most once per process — and a failed detailed detection must be
retried rather than cached as None.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

import fpstune.utils.detect as detect

DETAILED_STDOUT = """Name=AMD Ryzen 7 5800X
PhysicalCores=8
LogicalCores=16
BaseClock=3800
MaxClock=3800
L3Cache=32768
"""


@pytest.fixture(autouse=True)
def _fresh_cpu_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate each test from module-level cache state left by other tests."""
    monkeypatch.setattr(detect, "_cpu_info_cache", None)
    monkeypatch.setattr(detect, "_cpu_detailed_cache", None)
    monkeypatch.setattr(detect.sys, "platform", "win32")
    # Attribute only exists on Windows; the subprocess itself is mocked anyway.
    monkeypatch.setattr(detect.subprocess, "CREATE_NO_WINDOW", 0, raising=False)


def _proc(stdout: str) -> MagicMock:
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = stdout
    return proc


class TestGetCpuInfoCache:
    def test_second_call_spawns_no_new_subprocess(self) -> None:
        with patch.object(detect.subprocess, "run", return_value=_proc("AMD Ryzen 7 5800X")) as run:
            first = detect.get_cpu_info()
            calls_after_first = run.call_count
            second = detect.get_cpu_info()

        assert first["cpu_name"] == "AMD Ryzen 7 5800X"
        assert second == first
        # The regression this guards: every /api/system request re-spawned
        # PowerShell for a name that cannot change within a session.
        assert run.call_count == calls_after_first


class TestGetCpuDetailedInfoCache:
    def test_second_call_spawns_no_new_subprocess(self) -> None:
        with patch.object(detect.subprocess, "run", return_value=_proc(DETAILED_STDOUT)) as run:
            first = detect.get_cpu_detailed_info()
            calls_after_first = run.call_count
            second = detect.get_cpu_detailed_info()

        assert first is not None
        assert first.physical_cores == 8
        assert first.logical_cores == 16
        assert second is first
        assert run.call_count == calls_after_first

    def test_failed_detection_is_not_cached(self) -> None:
        """A transient failure must not pin the session to None forever."""
        with patch.object(
            detect.subprocess,
            "run",
            side_effect=[OSError("powershell unavailable"), _proc(DETAILED_STDOUT)],
        ) as run:
            assert detect.get_cpu_detailed_info() is None
            retried = detect.get_cpu_detailed_info()

        assert retried is not None
        assert retried.name == "AMD Ryzen 7 5800X"
        assert run.call_count == 2


class TestCacheLocksSpanTheSubprocess:
    """A cache whose check and store are separately locked still races (#22).

    Releasing the lock around the subprocess lets every concurrent caller read
    an empty cache and spawn its own PowerShell — the exact duplication the
    cache exists to prevent.
    """

    def _held_during(self, lock: threading.Lock, stdout: str, call) -> list[bool]:
        held: list[bool] = []

        def _run(*_args, **_kwargs):
            held.append(lock.locked())
            return _proc(stdout)

        with patch.object(detect.subprocess, "run", _run):
            call()
        return held

    def test_detailed_cpu_lock_is_held_across_the_subprocess(self) -> None:
        held = self._held_during(
            detect._cpu_detailed_lock, DETAILED_STDOUT, detect.get_cpu_detailed_info
        )
        assert held == [True]

    def test_basic_cpu_lock_is_held_across_the_subprocess(self) -> None:
        held = self._held_during(detect._cpu_info_lock, "AMD Ryzen 7 5800X", detect.get_cpu_info)
        assert held == [True]

    def test_os_info_lock_is_held_across_the_subprocess(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(detect, "_os_info_cache", None)
        held = self._held_during(
            detect._os_info_lock,
            "Edition=Windows 11 Pro\nDisplayVersion=24H2\n",
            detect._get_os_info_batch,
        )
        assert held == [True]

    def test_concurrent_callers_share_one_detailed_cpu_subprocess(self) -> None:
        calls = 0
        calls_lock = threading.Lock()
        start = threading.Barrier(8)

        def _run(*_args, **_kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
            return _proc(DETAILED_STDOUT)

        def _worker() -> None:
            start.wait(timeout=10)
            detect.get_cpu_detailed_info()

        with patch.object(detect.subprocess, "run", _run):
            threads = [threading.Thread(target=_worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        assert calls == 1
