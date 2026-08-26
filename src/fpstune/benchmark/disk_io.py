"""What the drive under a game library actually does.

`sources.py` carries two gaps that are the same gap: `storage_performance` is
"no disk benchmark in this build" and `loading_speed` is "no instrumented load
to time". Between them they cover every storage tweak fpstune ships — NVMe power
states, write caching, 8.3 name generation, TRIM — and none of those settings
has ever been checked on the machine it was applied to.

Two numbers, because a game asks the drive for two different things:

*Sequential throughput* is loading. A level is a small number of large reads,
and MB/s is what decides how long the loading screen lasts.

*4K random read* is streaming. Once the level is up, the drive is answering a
scattered stream of small requests while the frame loop waits on them, and the
number that matters there is not throughput but the tail: `random_read_p99_ms`
is the request that arrived late, and a request that arrives late while a texture
is needed is a hitch rather than a slower load.

**Three things that have to be true or the number is fiction**, and each is done
rather than hoped for:

*The cache has to be out of the way.* A file just written is in the standby list,
and reading it back measures RAM. Every read pass opens the file with
`FILE_FLAG_NO_BUFFERING` on Windows, which makes the request go to the device.
Where that flag does not exist the bench says so rather than reporting a number
that is really a memory bandwidth figure.

*The file has to be bigger than the cache is willing to hold*, so the sequential
pass cannot be served from what the write left behind.

*The file has to go away.* It is written under the caller's temp directory and
removed in a `finally`, including when the run is interrupted — a benchmark that
leaves a gigabyte behind has cost the user more than it told them.

Deliberately not measured: write endurance, queue depth scaling, mixed
read/write. Those are drive-characterisation questions, and this is here to
answer whether a setting fpstune changed moved anything.
"""

from __future__ import annotations

import ctypes
import os
import random
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

if sys.platform == "win32":
    from ctypes import wintypes

from fpstune.benchmark.suite import BenchReading, BenchResult
from fpstune.utils.logger import get_logger

logger = get_logger()

DEFAULT_FILE_MB = 256
"""Large enough that the sequential pass cannot come out of the standby list.

Small enough to write in a couple of seconds on anything modern, because this
runs twice per comparison and a user is waiting through both.
"""

DEFAULT_BLOCK_KB = 1024
"""The sequential request size. A game engine reads assets in chunks like this,
and a 4K sequential pass would measure the request path rather than the media."""

RANDOM_BLOCK_BYTES = 4096
"""4K because that is the page, the NTFS cluster, and what a streaming read is."""

DEFAULT_RANDOM_READS = 2000
"""Enough for a p99 to name a request that happened rather than round to the
worst of a handful."""

_RANDOM_SEED = 0x4D15C
"""The same offsets before and after. A fresh set would put the seek pattern
into the difference along with whatever the setting did."""

_NO_TEMP_SPACE = "not enough free space in the temp directory to write the test file"
_UNBUFFERED_UNAVAILABLE = (
    "this platform has no way to bypass the file cache, so a read would measure "
    "memory rather than the drive"
)

_SECTOR = 4096
"""Unbuffered I/O demands offsets, sizes and buffer addresses aligned to the
physical sector. 4096 covers every drive fpstune runs on, and over-aligning to
it is harmless on a 512-byte sector."""

# CreateFileW, not os.open. Measured 2026-08-24: `os.open` accepts
# FILE_FLAG_NO_BUFFERING without complaint and silently ignores it — an
# unaligned 1000-byte read, which real unbuffered I/O rejects outright,
# succeeded. Every read would have come out of the standby list, and this bench
# would have reported RAM bandwidth as a disk figure.
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_OPEN_EXISTING = 3
_FILE_FLAG_NO_BUFFERING = 0x20000000
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value if sys.platform == "win32" else -1


def _can_bypass_the_cache() -> bool:
    """Whether a read here can be made to reach the device."""
    return sys.platform == "win32"


class _UnbufferedReader:
    """A read handle that goes to the drive rather than to the cache.

    Sector alignment is not optional and is not checked politely by Windows: an
    unaligned offset, length or *buffer address* fails the read. The buffer is
    therefore over-allocated and an aligned address taken inside it, which is
    the standard way and the reason this is not three lines.
    """

    def __init__(self, path: Path, block_bytes: int) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateFileW.restype = wintypes.HANDLE
        self._block = _align_up(block_bytes)

        self._raw = ctypes.create_string_buffer(self._block + _SECTOR)
        offset = (-ctypes.addressof(self._raw)) % _SECTOR
        self._buffer = (ctypes.c_char * self._block).from_buffer(self._raw, offset)

        self._handle = self._kernel32.CreateFileW(
            str(path),
            _GENERIC_READ,
            _FILE_SHARE_READ,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_NO_BUFFERING,
            None,
        )
        if self._handle == _INVALID_HANDLE_VALUE:
            raise OSError(ctypes.get_last_error(), f"cannot open {path} unbuffered")

    def seek(self, offset: int) -> None:
        moved = ctypes.c_longlong(0)
        if not self._kernel32.SetFilePointerEx(
            self._handle, ctypes.c_longlong(offset), ctypes.byref(moved), 0
        ):
            raise OSError(ctypes.get_last_error(), f"cannot seek to {offset}")

    def read(self, length: int | None = None) -> int:
        """Read one block and return how many bytes came back."""
        wanted = self._block if length is None else length
        read = wintypes.DWORD(0)
        if not self._kernel32.ReadFile(
            self._handle, self._buffer, wanted, ctypes.byref(read), None
        ):
            raise OSError(ctypes.get_last_error(), "unbuffered read failed")
        return int(read.value)

    def close(self) -> None:
        self._kernel32.CloseHandle(self._handle)

    def __enter__(self) -> _UnbufferedReader:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _align_up(value: int) -> int:
    return ((value + _SECTOR - 1) // _SECTOR) * _SECTOR


class DiskIoBench:
    """Sequential throughput and 4K random-read latency on the temp volume."""

    key = "disk_io"
    label = "Disk throughput and latency"
    requires = "room for a temporary file on the drive holding your temp directory"

    def __init__(
        self,
        *,
        file_mb: int = DEFAULT_FILE_MB,
        block_kb: int = DEFAULT_BLOCK_KB,
        random_reads: int = DEFAULT_RANDOM_READS,
        directory: Path | None = None,
    ) -> None:
        if file_mb <= 0:
            raise ValueError("file_mb has to be positive to have anything to read")
        if block_kb <= 0:
            raise ValueError("block_kb has to be positive to have a request size")
        self.file_mb = file_mb
        self.block_kb = block_kb
        self.random_reads = random_reads
        self.directory = directory or Path(tempfile.gettempdir())

    def is_available(self) -> tuple[bool, str]:
        if not _can_bypass_the_cache():
            return False, _UNBUFFERED_UNAVAILABLE
        try:
            free = shutil.disk_usage(self.directory).free
        except OSError:
            return True, ""  # cannot tell; the write itself will fail loudly
        # Twice the file, so a nearly full disk is refused rather than filled.
        if free < self.file_mb * 1024 * 1024 * 2:
            return False, _NO_TEMP_SPACE
        return True, ""

    def _write_file(self, path: Path) -> float:
        """Write the test file and return the seconds it took."""
        block = os.urandom(self.block_kb * 1024)
        blocks = (self.file_mb * 1024) // self.block_kb

        started = time.perf_counter()
        with open(path, "wb", buffering=0) as handle:
            for _ in range(blocks):
                handle.write(block)
            handle.flush()
            os.fsync(handle.fileno())
        return time.perf_counter() - started

    def _sequential_read(self, path: Path) -> float:
        """Read the whole file past the cache and return MB/s."""
        size = path.stat().st_size

        started = time.perf_counter()
        with _UnbufferedReader(path, self.block_kb * 1024) as reader:
            while reader.read():
                pass
        elapsed = time.perf_counter() - started

        return (size / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0

    def _random_read(self, path: Path) -> list[float]:
        """One latency in milliseconds per 4K read, at seeded offsets."""
        size = path.stat().st_size
        last = max(0, (size - RANDOM_BLOCK_BYTES) // RANDOM_BLOCK_BYTES)
        rng = random.Random(_RANDOM_SEED)
        offsets = [rng.randint(0, last) * RANDOM_BLOCK_BYTES for _ in range(self.random_reads)]

        latencies: list[float] = []
        with _UnbufferedReader(path, RANDOM_BLOCK_BYTES) as reader:
            for offset in offsets:
                started = time.perf_counter()
                reader.seek(offset)
                reader.read(RANDOM_BLOCK_BYTES)
                latencies.append((time.perf_counter() - started) * 1000.0)
        return latencies

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        sequential: list[float] = []
        write_speed: list[float] = []
        random_median: list[float] = []
        random_p99: list[float] = []
        iops: list[float] = []

        handle, name = tempfile.mkstemp(prefix="fpstune-diskio-", suffix=".bin", dir=self.directory)
        os.close(handle)
        path = Path(name)

        try:
            for _ in range(repeats):
                write_seconds = self._write_file(path)
                write_speed.append(self.file_mb / write_seconds if write_seconds > 0 else 0.0)

                sequential.append(self._sequential_read(path))

                latencies = self._random_read(path)
                ranked = sorted(latencies)
                random_median.append(statistics.median(ranked))
                random_p99.append(ranked[min(len(ranked) - 1, int(len(ranked) * 0.99))])
                total_seconds = sum(latencies) / 1000.0
                iops.append(len(latencies) / total_seconds if total_seconds > 0 else 0.0)
        finally:
            # In a finally rather than after the loop: an interrupted run would
            # otherwise leave a quarter-gigabyte behind on the user's temp drive.
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Could not remove the disk benchmark file %s: %s", path, exc)

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
                "storage_performance": BenchReading(
                    "storage_performance", sequential, "MB/s", higher_is_better=True
                ),
                "sequential_write_mbps": BenchReading(
                    "sequential_write_mbps", write_speed, "MB/s", higher_is_better=True
                ),
                "random_read_iops": BenchReading(
                    "random_read_iops", iops, "IOPS", higher_is_better=True
                ),
                "random_read_ms": BenchReading(
                    "random_read_ms", random_median, "ms", higher_is_better=False
                ),
                # The tail is the number a streaming hitch lives in: the median
                # can hold while the worst 1% doubles, and it is the worst 1%
                # that arrives while a texture is needed.
                "random_read_p99_ms": BenchReading(
                    "random_read_p99_ms", random_p99, "ms", higher_is_better=False
                ),
            },
            detail={
                "file_mb": self.file_mb,
                "block_kb": self.block_kb,
                "random_reads": self.random_reads,
                "directory": str(self.directory),
                "cache_bypassed": True,
            },
            duration_seconds=time.perf_counter() - started,
        )
