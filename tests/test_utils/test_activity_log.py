"""Regression tests: ActivityLog.add is thread-safe and its trim loses nothing (#22).

``add`` is called from the sixteen bulk-apply worker threads. It had no lock,
and its trim was ``self._entries = self._entries[-max:]`` — a rebind. An append
landing between the slice and the assignment went into the list that was about
to be thrown away, so the activity line for that tweak silently vanished.
"""

from __future__ import annotations

import threading

from fpstune.utils.logger import ActivityLog


class TestTrimKeepsEveryAppend:
    def test_overflowing_the_log_never_rebinds_the_store(self) -> None:
        """The rebind is the loss window; a bounded deque has none."""
        log = ActivityLog(max_entries=4)
        store = log._entries  # noqa: SLF001

        for i in range(12):
            log.add(f"entry {i}")

        assert log._entries is store  # noqa: SLF001
        assert len(log._entries) == 4  # noqa: SLF001

    def test_overflow_keeps_the_newest_entries(self) -> None:
        log = ActivityLog(max_entries=3)
        for i in range(6):
            log.add(f"entry {i}")

        assert [e["message"] for e in log.get_entries(limit=50)] == [
            "entry 5",
            "entry 4",
            "entry 3",
        ]


class TestConcurrentAdds:
    def test_add_takes_the_lock(self) -> None:
        """Direct mechanism check: without it, the checks below are luck."""
        log = ActivityLog(max_entries=10)
        held: list[bool] = []
        real_lock = log._lock  # noqa: SLF001

        class _Observing:
            def __enter__(self):
                held.append(True)
                return real_lock.__enter__()

            def __exit__(self, *exc):
                return real_lock.__exit__(*exc)

        log._lock = _Observing()  # type: ignore[assignment]  # noqa: SLF001
        log.add("one entry")

        assert held == [True]

    def test_no_entry_is_lost_when_sixteen_workers_write_at_once(self) -> None:
        """One entry per bulk-apply worker per tweak; a lost one is a lost report."""
        workers = 16
        per_worker = 25
        log = ActivityLog(max_entries=workers * per_worker)
        start = threading.Barrier(workers)

        def _worker(worker_id: int) -> None:
            start.wait(timeout=10)
            for i in range(per_worker):
                log.add(f"worker {worker_id} entry {i}")

        threads = [threading.Thread(target=_worker, args=(w,)) for w in range(workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        messages = {e["message"] for e in log.get_entries(limit=workers * per_worker)}
        expected = {f"worker {w} entry {i}" for w in range(workers) for i in range(per_worker)}
        assert messages == expected

    def test_reader_sees_a_consistent_snapshot_during_concurrent_writes(self) -> None:
        """get_entries must never observe the store mid-mutation."""
        log = ActivityLog(max_entries=50)
        stop = threading.Event()
        failures: list[str] = []

        def _writer() -> None:
            i = 0
            while not stop.is_set():
                log.add(f"entry {i}")
                i += 1

        def _reader() -> None:
            for _ in range(200):
                entries = log.get_entries(limit=50)
                if len(entries) > 50:
                    failures.append(f"snapshot held {len(entries)} entries")
                if any("message" not in e for e in entries):
                    failures.append("snapshot held a malformed entry")

        writer = threading.Thread(target=_writer)
        writer.start()
        try:
            _reader()
        finally:
            stop.set()
            writer.join(timeout=10)

        assert failures == []
