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
