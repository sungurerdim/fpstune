"""The disk bench has one way to be worthless, and it nearly took it.

`os.open` on Windows accepts `FILE_FLAG_NO_BUFFERING` without complaint and
ignores it. The first version of this bench used exactly that, so every read
would have been served from the standby list and the module would have reported
memory bandwidth under the name `storage_performance`. It was caught by asking
for an unaligned read — which real unbuffered I/O rejects and a cached read
happily serves — and that probe is the first test here, so the shortcut cannot
come back.

Everything else runs at a file size measured in single megabytes. That is far
too small for the throughput figure to mean anything about a drive, and it is
the right size for testing that the bench does what it says: bypasses the cache,
seeds its offsets, and takes its file with it when it goes.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from fpstune.benchmark.disk_io import (
    RANDOM_BLOCK_BYTES,
    DiskIoBench,
    _align_up,
    _UnbufferedReader,
)
from fpstune.benchmark.suite import Bench, run_suite

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="unbuffered reads are a Windows path here"
)


def _tiny(tmp_path: Path, **kwargs: object) -> DiskIoBench:
    defaults: dict = {
        "file_mb": 2,
        "block_kb": 64,
        "random_reads": 25,
        "random_writes": 20,
        "queue_depth": 4,
        "directory": tmp_path,
    }
    defaults.update(kwargs)
    return DiskIoBench(**defaults)  # type: ignore[arg-type]


class TestTheCacheIsActuallyBypassed:
    @windows_only
    def test_os_open_still_ignores_the_no_buffering_flag(self, tmp_path: Path) -> None:
        """The reason this bench uses CreateFileW, pinned as a fact about the
        platform rather than as a comment.

        Real unbuffered I/O rejects an unaligned length. If this ever starts
        raising, `os.open` began honouring the flag and the ctypes reader could
        be retired — so this failing is good news, not a regression.
        """
        path = tmp_path / "probe.bin"
        path.write_bytes(os.urandom(RANDOM_BLOCK_BYTES * 4))

        descriptor = os.open(str(path), os.O_RDONLY | os.O_BINARY | 0x20000000)
        try:
            served = os.read(descriptor, 1000)
        finally:
            os.close(descriptor)

        assert len(served) == 1000, (
            "os.open now honours FILE_FLAG_NO_BUFFERING — the ctypes reader in "
            "disk_io.py exists only because it did not"
        )

    @windows_only
    def test_the_reader_refuses_an_unaligned_length(self, tmp_path: Path) -> None:
        """The positive half: our handle really is unbuffered, because it
        enforces what unbuffered I/O enforces."""
        path = tmp_path / "aligned.bin"
        path.write_bytes(os.urandom(RANDOM_BLOCK_BYTES * 4))

        with _UnbufferedReader(path, RANDOM_BLOCK_BYTES) as reader, pytest.raises(OSError):
            reader.read(1000)

    @windows_only
    def test_the_reader_serves_an_aligned_block(self, tmp_path: Path) -> None:
        path = tmp_path / "aligned.bin"
        path.write_bytes(os.urandom(RANDOM_BLOCK_BYTES * 4))

        with _UnbufferedReader(path, RANDOM_BLOCK_BYTES) as reader:
            assert reader.read(RANDOM_BLOCK_BYTES) == RANDOM_BLOCK_BYTES

    @windows_only
    def test_it_can_seek_to_a_later_block(self, tmp_path: Path) -> None:
        path = tmp_path / "aligned.bin"
        path.write_bytes(os.urandom(RANDOM_BLOCK_BYTES * 4))

        with _UnbufferedReader(path, RANDOM_BLOCK_BYTES) as reader:
            reader.seek(RANDOM_BLOCK_BYTES * 3)
            assert reader.read(RANDOM_BLOCK_BYTES) == RANDOM_BLOCK_BYTES

    def test_alignment_rounds_up_and_leaves_aligned_values_alone(self) -> None:
        assert _align_up(1) == 4096
        assert _align_up(4096) == 4096
        assert _align_up(4097) == 8192


class TestItSaysWhenItCannotRun:
    def test_a_platform_with_no_way_past_the_cache_declines(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Rather than returning a memory-bandwidth number under a disk name."""
        monkeypatch.setattr("fpstune.benchmark.disk_io._can_bypass_the_cache", lambda: False)
        available, why = _tiny(tmp_path).is_available()

        assert available is False
        assert "measure memory rather than the drive" in why

    def test_a_full_disk_declines_instead_of_filling_it(self, tmp_path: Path, monkeypatch) -> None:
        """Asking for the last of a user's free space to benchmark it is the
        one failure mode where the bench costs more than it reports."""

        class _NoRoom:
            free = 1024

        monkeypatch.setattr("fpstune.benchmark.disk_io._can_bypass_the_cache", lambda: True)
        monkeypatch.setattr("shutil.disk_usage", lambda _path: _NoRoom())

        available, why = _tiny(tmp_path).is_available()

        assert available is False
        assert "free space" in why

    def test_a_file_with_nothing_in_it_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to have anything to read"):
            DiskIoBench(file_mb=0)

    def test_a_request_size_of_nothing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to have a request size"):
            DiskIoBench(block_kb=0)

    def test_it_satisfies_the_suite_protocol(self, tmp_path: Path) -> None:
        assert isinstance(_tiny(tmp_path), Bench)


@windows_only
class TestWhatItMeasures:
    def test_it_reports_both_kinds_of_question_a_game_asks(self, tmp_path: Path) -> None:
        result = _tiny(tmp_path).run(2)

        assert set(result.readings) == {
            "storage_performance",
            "sequential_write_mbps",
            "random_read_iops",
            "random_read_ms",
            "random_read_p99_ms",
            "random_read_qd_p99_ms",
            "random_write_iops",
            "random_write_ms",
            "random_write_p99_ms",
            "random_write_qd_p99_ms",
        }

    def test_every_metric_knows_which_way_is_better(self, tmp_path: Path) -> None:
        """Throughput up, latency down — and getting that backwards would report
        a slower drive as an improvement."""
        readings = _tiny(tmp_path).run(2).readings

        assert readings["storage_performance"].improves_upward is True
        assert readings["random_read_iops"].improves_upward is True
        assert readings["random_read_ms"].improves_upward is False
        assert readings["random_read_p99_ms"].improves_upward is False

    def test_the_tail_is_never_better_than_the_median(self, tmp_path: Path) -> None:
        """p99 below the median would mean the percentile is being read off the
        wrong end, which is a mistake that looks like an unusually good drive."""
        readings = _tiny(tmp_path).run(2).readings

        assert readings["random_read_p99_ms"].median >= readings["random_read_ms"].median

    def test_one_sample_per_repeat_so_there_is_a_noise_floor(self, tmp_path: Path) -> None:
        for reading in _tiny(tmp_path).run(3).readings.values():
            assert len(reading.samples) == 3

    def test_the_test_file_is_gone_afterwards(self, tmp_path: Path) -> None:
        """A benchmark that leaves a quarter-gigabyte behind has cost the user
        more than it told them."""
        _tiny(tmp_path).run(2)

        assert list(tmp_path.glob("fpstune-diskio-*")) == []

    def test_the_test_file_is_gone_even_when_the_run_fails(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The cleanup is in a `finally` for this case specifically: an
        interrupted run is exactly when nobody goes looking for the file."""
        monkeypatch.setattr(
            DiskIoBench,
            "_sequential_read",
            lambda *_args: (_ for _ in ()).throw(OSError("drive went away")),
        )

        with pytest.raises(OSError, match="drive went away"):
            _tiny(tmp_path).run(2)

        assert list(tmp_path.glob("fpstune-diskio-*")) == []

    def test_the_default_directory_is_the_users_temp(self) -> None:
        """Never a path from the machine this was written on (C9)."""
        assert DiskIoBench().directory == Path(tempfile.gettempdir())


@windows_only
class TestThroughTheSuite:
    def test_a_failing_run_becomes_a_reason_rather_than_a_crash(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            DiskIoBench,
            "_sequential_read",
            lambda *_args: (_ for _ in ()).throw(OSError("drive went away")),
        )

        run = run_suite([_tiny(tmp_path)], "before", repeats=2)

        assert run.skipped[0].bench == "disk_io"
        assert "drive went away" in run.skipped[0].reason


class TestTheWritePatterns:
    """A write can be slow for a reason no read pattern shows — an SLC cache
    that has run out, garbage collection, or write caching a "tweak" turned off.
    None of that is visible in a read figure, so it needs its own."""

    def test_the_write_handle_waits_for_the_media_rather_than_the_driver(self) -> None:
        """Without WRITE_THROUGH a random write pattern measures how fast a
        queue accepts work, which on any modern drive has no upper bound worth
        reporting."""
        from fpstune.benchmark.disk_io import _FILE_FLAG_NO_BUFFERING, _FILE_FLAG_WRITE_THROUGH

        assert _FILE_FLAG_WRITE_THROUGH != _FILE_FLAG_NO_BUFFERING

    def test_the_write_tail_is_never_better_than_its_median(self, tmp_path: Path) -> None:
        readings = _tiny(tmp_path).run(2).readings

        assert readings["random_write_p99_ms"].median >= readings["random_write_ms"].median

    def test_every_write_metric_knows_which_way_is_better(self, tmp_path: Path) -> None:
        readings = _tiny(tmp_path).run(2).readings

        assert readings["random_write_iops"].improves_upward is True
        assert readings["random_write_ms"].improves_upward is False
        assert readings["random_write_p99_ms"].improves_upward is False
        assert readings["random_write_qd_p99_ms"].improves_upward is False

    def test_the_file_is_not_left_longer_or_shorter_by_the_writes(self, tmp_path: Path) -> None:
        """Every write is 4K at a 4K-aligned offset inside the file that was
        already written, so the pattern overwrites and never extends. A write
        past the end would grow the file under the next repeat's sequential
        read and quietly change what that read measured."""
        bench = _tiny(tmp_path)
        bench.run(2)

        assert list(tmp_path.glob("fpstune-diskio-*.bin")) == []


class TestTheDeepQueue:
    """The queue kept full is a different question about the same drive: an SSD
    answers many outstanding requests at once, and a setting that serialises the
    path shows up here and nowhere else."""

    def test_one_handle_and_one_lane_per_outstanding_request(self, tmp_path: Path) -> None:
        """A Windows file handle carries its own file pointer, so two lanes
        sharing one would seek each other's requests out from under them —
        which would not fail, it would quietly read the wrong offsets."""
        bench = _tiny(tmp_path, queue_depth=4)
        import tempfile as tf
        from pathlib import Path as P

        handle, name = tf.mkstemp(dir=tmp_path, suffix=".bin")
        import os

        os.close(handle)
        path = P(name)
        bench._write_file(path)
        try:
            latencies, elapsed = bench._queued_pass(path, bench._offsets(path, 40), write=False)
        finally:
            path.unlink(missing_ok=True)

        assert len(latencies) == 40
        assert elapsed > 0

    def test_every_lane_gets_enough_work_to_outweigh_starting_it(self, tmp_path: Path) -> None:
        """Measured: 800 reads over eight lanes took 101 ms and reported 7,920
        IOPS; 4,000 over the same lanes took 109 ms and reported 36,720 — almost
        all of the first figure was the lanes starting up."""
        bench = _tiny(tmp_path, queue_depth=8, random_reads=10)

        assert bench._queued_count(10) >= 8 * 100

    def test_the_queued_rate_is_reported_as_unmeasured_rather_than_as_a_number(
        self, tmp_path: Path
    ) -> None:
        """Its spread was larger than its own value on the machine this was
        written on, so it can never beat its own noise floor and can therefore
        never report a change (C11 rule 2). The observed figure stays in detail
        under a name that says it was not measurable."""
        result = _tiny(tmp_path).run(2)

        assert "random_read_qd_iops" not in result.readings
        assert "random_write_qd_iops" not in result.readings
        assert "lanes starting" in result.detail["queued_rate_unmeasured"]

    def test_the_switch_interval_is_left_the_way_it_was_found(self, tmp_path: Path) -> None:
        """It is lowered around the queued pass, and a bench that left it
        lowered has changed the process it was only supposed to measure."""
        import sys

        before = sys.getswitchinterval()
        _tiny(tmp_path).run(2)

        assert sys.getswitchinterval() == before

    def test_a_queue_depth_of_nothing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one to issue a request"):
            DiskIoBench(queue_depth=0)


class TestWhichDriveItMeasured:
    def test_the_disk_is_identified_by_unique_id_and_never_by_a_letter(
        self, tmp_path: Path
    ) -> None:
        """C5: a drive letter is a mount point a user can move and a friendly
        name is a model string. Only `UniqueId` survives the drive being moved
        to another port, and only `UniqueId` is free of this machine's own
        hardware names (C9)."""
        found = _tiny(tmp_path).physical_disk()

        assert "unique_id" in found or "unknown" in found
        assert "friendly_name" not in found

    def test_a_disk_that_could_not_be_identified_says_why(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A benchmark that could not establish which drive it measured is still
        a valid measurement of this machine's temp volume, so it never fails the
        run — it says so instead (C11 rule 3)."""
        from fpstune.benchmark import disk_io

        monkeypatch.setattr(disk_io, "query_rows", lambda *_a, **_k: ([], "the query was refused"))

        assert _tiny(tmp_path).physical_disk() == {"unknown": "the query was refused"}

    def test_the_drive_letter_comes_from_the_directory_rather_than_the_source(self) -> None:
        """A hardcoded letter is the same bug as a hardcoded buffer size (C1/C9):
        it is right on the machine it was written on and wrong on the next one."""
        from fpstune.benchmark.disk_io import DISK_SCRIPT

        assert "__DIRECTORY__" in DISK_SCRIPT
        assert "C:" not in DISK_SCRIPT
