"""What the drive under a game library actually does.

`sources.py` carries two gaps that are the same gap: `storage_performance` is
"no disk benchmark in this build" and `loading_speed` is "no instrumented load
to time". Between them they cover every storage tweak fpstune ships — NVMe power
states, write caching, 8.3 name generation, TRIM — and none of those settings
has ever been checked on the machine it was applied to.

Four patterns, because a game asks the drive for four different things:

*Sequential throughput* is loading. A level is a small number of large reads,
and MB/s is what decides how long the loading screen lasts. Written as well as
read, because a shader cache being rebuilt and a save being flushed are writes.

*4K random read at queue depth 1* is streaming. Once the level is up, the drive
is answering a scattered stream of small requests while the frame loop waits on
them, and the number that matters there is not throughput but the tail:
`random_read_p99_ms` is the request that arrived late, and a request that
arrives late while a texture is needed is a hitch rather than a slower load.

*4K random read at queue depth 32* is the same requests with the queue kept
full, and it is a different question about the same drive. An SSD's controller
answers many outstanding requests in parallel, so this is where a setting that
serialises the queue (write caching off, a power state that will not stay awake,
a filter driver in the path) does its damage. What is reported from this pattern
is its *tail* and not its rate: each request times itself, so the tail is solid,
while a rate has to be divided by a wall clock that includes the lanes starting
— and measured here that made its spread larger than its own value. The rate is
still in `detail` under a name that says it was not measurable; the reason is
there beside it.

*4K random write* is the one pattern that can be slow for a reason the read
patterns never show — an SLC cache that has run out, a controller doing garbage
collection, or write caching that has been turned off by a "tweak". It is
measured at both queue depths for the same reason the reads are.

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

**Which drive.** The temp volume, which is the system drive on a stock install,
and its physical disk is named in `detail` by `UniqueId` (C5) rather than by a
letter or an enumeration order — the one key that survives the drive being moved
to another port. A sweep over every physical disk is deliberately not done: the
other drives may hold no writable volume, and a benchmark that filled a user's
second SSD to measure it has cost more than it reported.

Deliberately not measured: write endurance and mixed read/write. Those are
drive-characterisation questions, and this is here to answer whether a setting
fpstune changed moved anything.
"""

from __future__ import annotations

import ctypes
import os
import random
import shutil
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

if sys.platform == "win32":
    from ctypes import wintypes

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.benchmark.win_query import query_rows
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

_SLOW_DISK_MBPS = 40.0
"""A floor, not an estimate: comfortably under a spinning disk's rate."""

_SLOW_SEEK_SECONDS = 0.012
"""12 ms per random read — a seeking HDD, orders of magnitude above an SSD."""


DEFAULT_QUEUE_DEPTH = 32
"""How many 4K requests are kept outstanding for the deep-queue pattern.

32 because that is where a consumer NVMe drive's own parallelism has arrived and
before the point where the number becomes about the driver's queue rather than
the media. One thread per outstanding request, each on its own handle: a Windows
file handle carries the file pointer, so two threads sharing one would seek each
other's reads out from under them.
"""

_QUEUED_REQUESTS_PER_LANE = 100
"""The floor on how many requests each lane issues, and it is a floor on noise.

Starting a lane costs a thread and a handle, and that cost does not shrink when
the lane has less to do. Measured here: 800 reads spread over eight lanes took
101 ms and reported 7,920 IOPS; 4,000 reads over the same eight lanes took
109 ms and reported 36,720 — the same wall clock, because almost all of the
first figure was the lanes starting up. A reading that swings by five times
depending on how much work it was given never beats its own noise floor and can
therefore never report a change, which is a reading that costs seconds and says
nothing.
"""

_QUEUED_SWITCH_INTERVAL = 50e-6
"""How long a thread may hold the GIL while the deep queue is running.

Fifty microseconds, against CPython's 5 ms default. Set for the duration of the
queued pass and restored afterwards — see `_queued_pass` for the measurement
that decided it, and for why the default turned a deeper queue into a slower
one.
"""

DEFAULT_RANDOM_WRITES = 1000
"""Fewer than the reads, on purpose. Every one of them is an erase-modify-write
somewhere on the media, and this bench runs on the user's own drive."""

DEFAULT_RANDOM_READS = 2000
"""Enough for a p99 to name a request that happened rather than round to the
worst of a handful."""

_RANDOM_SEED = 0x4D15C
"""The same offsets before and after. A fresh set would put the seek pattern
into the difference along with whatever the setting did."""

DISK_SCRIPT = (
    "$d=(Get-Item -LiteralPath '__DIRECTORY__').PSDrive.Name; "
    "@(Get-Partition -DriveLetter $d -ErrorAction SilentlyContinue | "
    "Get-Disk -ErrorAction SilentlyContinue | ForEach-Object { [pscustomobject]@{"
    "unique_id=$_.UniqueId;"
    "bus_type=[string]$_.BusType;"
    "media_type=[string]$_.MediaType"
    "} })"
)
"""Which physical disk the temp directory actually lives on.

The drive letter is derived from the directory rather than assumed, and the
answer is kept by `UniqueId` (C5) — never the letter, never the friendly name,
never the enumeration order. A letter is a mount point a user can move and a
friendly name is a model string, which is exactly the class of literal C9
forbids carrying anywhere.

`__DIRECTORY__` is substituted rather than `str.format`-ed: the script is full of
PowerShell's own braces, and `format` reads every one of them as a field.
"""

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
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_FILE_FLAG_NO_BUFFERING = 0x20000000
_FILE_FLAG_WRITE_THROUGH = 0x80000000
"""Both flags on the write handle, and they are not the same thing.

`NO_BUFFERING` keeps the data out of the file cache on the way down.
`WRITE_THROUGH` makes the call wait for the drive to say it has the data rather
than for the driver to say it has taken it. Without the second one a random
write pattern measures how fast a queue accepts work, which on any modern drive
is a number with no upper bound worth reporting.
"""
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value if sys.platform == "win32" else -1


def _can_bypass_the_cache() -> bool:
    """Whether a read here can be made to reach the device."""
    return sys.platform == "win32"


class _UnbufferedReader:
    """A handle that goes to the drive rather than to the cache.

    Sector alignment is not optional and is not checked politely by Windows: an
    unaligned offset, length or *buffer address* fails the read. The buffer is
    therefore over-allocated and an aligned address taken inside it, which is
    the standard way and the reason this is not three lines.
    """

    def __init__(self, path: Path, block_bytes: int, *, writable: bool = False) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateFileW.restype = wintypes.HANDLE
        self._block = _align_up(block_bytes)

        self._raw = ctypes.create_string_buffer(self._block + _SECTOR)
        offset = (-ctypes.addressof(self._raw)) % _SECTOR
        self._buffer = (ctypes.c_char * self._block).from_buffer(self._raw, offset)

        access = _GENERIC_READ | _GENERIC_WRITE if writable else _GENERIC_READ
        share = _FILE_SHARE_READ | _FILE_SHARE_WRITE if writable else _FILE_SHARE_READ
        flags = _FILE_FLAG_NO_BUFFERING
        if writable:
            # Wait for the media rather than for the driver — see the flag's own
            # note. A random write pattern without this measures a queue.
            flags |= _FILE_FLAG_WRITE_THROUGH

        self._handle = self._kernel32.CreateFileW(
            str(path),
            access,
            share,
            None,
            _OPEN_EXISTING,
            flags,
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

    def write(self, length: int | None = None) -> int:
        """Write one block from the aligned buffer and return how many bytes went.

        The buffer's contents are whatever the last read left there, which is
        exactly right: what is being measured is the drive taking 4096 aligned
        bytes, and inventing fresh bytes per write would put `os.urandom` inside
        the timed section.
        """
        wanted = self._block if length is None else length
        written = wintypes.DWORD(0)
        if not self._kernel32.WriteFile(
            self._handle, self._buffer, wanted, ctypes.byref(written), None
        ):
            raise OSError(ctypes.get_last_error(), "unbuffered write failed")
        return int(written.value)

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
        random_writes: int = DEFAULT_RANDOM_WRITES,
        queue_depth: int = DEFAULT_QUEUE_DEPTH,
        directory: Path | None = None,
    ) -> None:
        if file_mb <= 0:
            raise ValueError("file_mb has to be positive to have anything to read")
        if block_kb <= 0:
            raise ValueError("block_kb has to be positive to have a request size")
        if queue_depth < 1:
            raise ValueError("queue_depth has to be at least one to issue a request")
        self.file_mb = file_mb
        self.block_kb = block_kb
        self.random_reads = random_reads
        self.random_writes = random_writes
        self.queue_depth = queue_depth
        self.directory = directory or Path(tempfile.gettempdir())

    def timeout_seconds(self, repeats: int) -> float:
        """Derived from the file it writes and the random reads it takes.

        `_SLOW_DISK_MBPS` is a floor rather than an estimate — well under a
        spinning disk's sequential rate — because this figure only decides when
        to give up, and a deadline that a slow-but-working drive trips would
        turn every measurement on that machine into a missing one.
        """
        sequential = (self.file_mb / _SLOW_DISK_MBPS) * 2  # written, then read
        # The deep-queue pass issues the same number of requests as the shallow
        # one, so it is budgeted at the same cost rather than at a fraction of
        # it: the whole point of the pattern is that a drive which cannot
        # parallelise takes just as long with the queue full.
        random = (
            self.random_reads
            + self.random_writes
            + self._queued_count(self.random_reads)
            + self._queued_count(self.random_writes)
        ) * _SLOW_SEEK_SECONDS
        return deadline_for(sequential + random, repeats)

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

    def _queued_count(self, base: int) -> int:
        """How many requests the deep-queue pass issues.

        At least `_QUEUED_REQUESTS_PER_LANE` for every lane, because a lane's
        start-up cost is paid whether it does one request or a hundred — see
        that constant for the measurement. Never fewer than the shallow pass
        issues, so the two patterns are never compared across different amounts
        of work.
        """
        return max(base, self.queue_depth * _QUEUED_REQUESTS_PER_LANE)

    def _offsets(self, path: Path, count: int) -> list[int]:
        """Seeded 4K-aligned offsets inside the file.

        The same offsets before and after, so the seek pattern does not end up
        in the difference along with whatever the setting did.
        """
        size = path.stat().st_size
        last = max(0, (size - RANDOM_BLOCK_BYTES) // RANDOM_BLOCK_BYTES)
        rng = random.Random(_RANDOM_SEED)
        return [rng.randint(0, last) * RANDOM_BLOCK_BYTES for _ in range(count)]

    def _random_pass(self, path: Path, offsets: list[int], *, write: bool) -> list[float]:
        """One latency in milliseconds per 4K request, one at a time."""
        latencies: list[float] = []
        with _UnbufferedReader(path, RANDOM_BLOCK_BYTES, writable=write) as handle:
            for offset in offsets:
                started = time.perf_counter()
                handle.seek(offset)
                if write:
                    handle.write(RANDOM_BLOCK_BYTES)
                else:
                    handle.read(RANDOM_BLOCK_BYTES)
                latencies.append((time.perf_counter() - started) * 1000.0)
        return latencies

    def _random_read(self, path: Path) -> list[float]:
        """One latency in milliseconds per 4K read, at seeded offsets."""
        return self._random_pass(path, self._offsets(path, self.random_reads), write=False)

    def _queued_pass(
        self, path: Path, offsets: list[int], *, write: bool
    ) -> tuple[list[float], float]:
        """The same requests with `queue_depth` of them outstanding at once.

        One thread and one handle per outstanding request. Both are necessary
        and for different reasons: a Windows file handle carries its own file
        pointer, so two threads sharing one would seek each other's requests out
        from under them; and the work has to be on separate threads at all
        because `ReadFile` is where the wait happens. `ctypes` releases the GIL
        for the duration of a foreign call, so those waits genuinely overlap —
        which is the difference between a queue depth of 32 and 32 requests in a
        row.

        Releasing the GIL is necessary and was not sufficient. Each lane needs
        it back to run the handful of Python statements between two requests,
        and the default 5 ms switch interval meant a lane that had finished a
        100 microsecond read waited milliseconds behind another lane before it
        could issue the next one. Measured on this machine, 800 reads at queue
        depth 8: 8,586 IOPS at the default interval against 10,509 at queue
        depth 1 — the deep queue coming out *slower* than the shallow one. At
        50 microseconds the same pass reached 50,397 IOPS, which is the drive
        answering rather than the interpreter. So the interval is lowered for
        the pass and restored in a `finally`, the same discipline `memory.py`
        applies to the garbage collector: a benchmark may not leave the process
        it measured in a state it changed.

        Every request's own latency is kept, so the tail is the tail of the
        whole pattern rather than of one thread's share of it. The wall clock
        comes back beside them because it is the only honest denominator for a
        queued IOPS figure: the lanes overlap, so the sum of their latencies is
        several times the time the pattern actually took, and dividing by it
        reports a drive that got *slower* with a deeper queue. Measured here
        before the fix — 8969 IOPS at QD1 against 1203 at QD8 on the same NVMe
        drive, which is the arithmetic talking rather than the media.
        """
        lanes: list[list[int]] = [
            offsets[lane :: self.queue_depth] for lane in range(self.queue_depth)
        ]
        results: list[list[float]] = [[] for _ in lanes]
        failures: list[BaseException] = []
        ready = threading.Barrier(len(lanes))

        def run_lane(index: int) -> None:
            try:
                with _UnbufferedReader(path, RANDOM_BLOCK_BYTES, writable=write) as handle:
                    # Every lane opens its handle before any lane issues a
                    # request. Without the barrier the first lanes would finish
                    # their share while the last were still calling CreateFileW,
                    # and the queue would never actually be full.
                    ready.wait(timeout=30)
                    for offset in lanes[index]:
                        started = time.perf_counter()
                        handle.seek(offset)
                        if write:
                            handle.write(RANDOM_BLOCK_BYTES)
                        else:
                            handle.read(RANDOM_BLOCK_BYTES)
                        results[index].append((time.perf_counter() - started) * 1000.0)
            except BaseException as exc:  # noqa: BLE001 - carried back to the caller
                failures.append(exc)

        threads = [
            threading.Thread(target=run_lane, args=(index,), name=f"disk-qd-{index}")
            for index in range(len(lanes))
        ]
        previous_interval = sys.getswitchinterval()
        sys.setswitchinterval(_QUEUED_SWITCH_INTERVAL)
        try:
            started = time.perf_counter()
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            elapsed = time.perf_counter() - started
        finally:
            sys.setswitchinterval(previous_interval)

        if failures:
            raise failures[0]
        return [latency for lane in results for latency in lane], elapsed

    def physical_disk(self) -> dict[str, str]:
        """Which physical disk the test file lands on, by `UniqueId`.

        Empty with a reason rather than guessed. A benchmark that could not
        establish which drive it measured is still a valid measurement of *this*
        machine's temp volume, so this never fails the run — it just says so.
        """
        rows, reason = query_rows(
            DISK_SCRIPT.replace("__DIRECTORY__", str(self.directory).replace("'", "''")),
            timeout=30,
            component="benchmark.disk_io",
        )
        if reason:
            return {"unknown": reason}
        if not rows:
            return {
                "unknown": "no physical disk answered for the volume holding the temp directory"
            }
        row = rows[0]
        return {
            # `UniqueId` and nothing else: a drive letter is a mount point a
            # user can move, and a friendly name is a model string (C5, C9).
            "unique_id": str(row.get("unique_id") or ""),
            "bus_type": str(row.get("bus_type") or ""),
            "media_type": str(row.get("media_type") or ""),
        }

    @staticmethod
    def _tail(latencies: list[float], seconds: float | None = None) -> tuple[float, float, float]:
        """Median, p99 and IOPS for one pattern's latencies.

        `seconds` is the wall clock the pattern took, and it is required for
        anything issued in parallel. Without it the rate falls back to requests
        over the sum of their own latencies, which is correct only while exactly
        one request is outstanding — with eight lanes overlapping it reports a
        rate eight times too low, and a drive that went faster with a deeper
        queue as one that went slower.
        """
        if not latencies:
            return 0.0, 0.0, 0.0
        ranked = sorted(latencies)
        p99 = ranked[min(len(ranked) - 1, int(len(ranked) * 0.99))]
        total_seconds = sum(latencies) / 1000.0 if seconds is None else seconds
        served = len(latencies) / total_seconds if total_seconds > 0 else 0.0
        return statistics.median(ranked), p99, served

    # metric -> (unit, whether a bigger number is a better one). One table
    # rather than ten constructor calls: with the patterns doubled the readings
    # block was the largest thing in `run`, and a list of pairs is where a
    # direction typo is visible. Getting one of these backwards reports a slower
    # drive as an improvement, which is the mistake the table exists to make
    # readable.
    _READINGS: tuple[tuple[str, str, bool], ...] = (
        ("storage_performance", "MB/s", True),
        ("sequential_write_mbps", "MB/s", True),
        ("random_read_iops", "IOPS", True),
        ("random_read_ms", "ms", False),
        # The tail is the number a streaming hitch lives in: the median can hold
        # while the worst 1% doubles, and it is the worst 1% that arrives while
        # a texture is needed.
        ("random_read_p99_ms", "ms", False),
        # The queue kept full. Where a setting that serialises the path does its
        # damage: a drive whose QD1 tail holds while this one grows has lost
        # exactly the parallelism a game's streaming depends on. The tail and
        # not the rate — see `queued_rate_unmeasured` in `detail` for why.
        ("random_read_qd_p99_ms", "ms", False),
        # Writes, which go slow for reasons no read pattern shows — an SLC cache
        # that has run out, garbage collection, or write caching a "tweak"
        # turned off.
        ("random_write_iops", "IOPS", True),
        ("random_write_ms", "ms", False),
        ("random_write_p99_ms", "ms", False),
        ("random_write_qd_p99_ms", "ms", False),
    )

    def _one_repeat(self, path: Path) -> dict[str, float]:
        """Every pattern once, over the same file, in one dictionary.

        Split out of `run` so that adding a pattern is one entry here and one in
        `_READINGS` rather than three more accumulator lists threaded through a
        loop.
        """
        write_seconds = self._write_file(path)
        read_offsets = self._offsets(path, self.random_reads)
        write_offsets = self._offsets(path, self.random_writes)

        read_median, read_p99, read_iops = self._tail(
            self._random_pass(path, read_offsets, write=False)
        )
        write_median, write_p99, write_iops = self._tail(
            self._random_pass(path, write_offsets, write=True)
        )

        # The deep queue, against the wall clock — see `_tail` for why the
        # denominator is not the sum of the latencies once the lanes overlap.
        queued_reads, read_elapsed = self._queued_pass(
            path, self._offsets(path, self._queued_count(self.random_reads)), write=False
        )
        _, queued_read_p99, queued_read_iops = self._tail(queued_reads, read_elapsed)

        queued_writes, write_elapsed = self._queued_pass(
            path, self._offsets(path, self._queued_count(self.random_writes)), write=True
        )
        _, queued_write_p99, queued_write_iops = self._tail(queued_writes, write_elapsed)

        return {
            "storage_performance": self._sequential_read(path),
            "sequential_write_mbps": self.file_mb / write_seconds if write_seconds > 0 else 0.0,
            "random_read_iops": read_iops,
            "random_read_ms": read_median,
            "random_read_p99_ms": read_p99,
            "random_read_qd_p99_ms": queued_read_p99,
            "random_write_iops": write_iops,
            "random_write_ms": write_median,
            "random_write_p99_ms": write_p99,
            "random_write_qd_p99_ms": queued_write_p99,
            # Not published as readings — their spread exceeded their own value.
            # Carried here so `detail` can report what was observed under a name
            # that says it was not measurable.
            "queued_read_iops_observed": queued_read_iops,
            "queued_write_iops_observed": queued_write_iops,
        }

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()
        series: dict[str, list[float]] = {}

        handle, name = tempfile.mkstemp(prefix="fpstune-diskio-", suffix=".bin", dir=self.directory)
        os.close(handle)
        path = Path(name)

        try:
            for _ in range(repeats):
                for metric, value in self._one_repeat(path).items():
                    series.setdefault(metric, []).append(value)
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
                metric: BenchReading(metric, series[metric], unit, higher_is_better=upward)
                for metric, unit, upward in self._READINGS
            },
            detail={
                "file_mb": self.file_mb,
                "block_kb": self.block_kb,
                "random_reads": self.random_reads,
                "random_writes": self.random_writes,
                "queue_depth": self.queue_depth,
                "queued_reads": self._queued_count(self.random_reads),
                "queued_writes": self._queued_count(self.random_writes),
                # Measured on this machine over three repeats at the defaults:
                # a queued read rate of 9,479 IOPS with a noise floor of 16,715,
                # and a queued write rate of 30,161 with a floor of 25,055. A
                # reading whose spread is larger than its value can never beat
                # its own noise and therefore can never report a change (C11
                # rule 2) — the lane start-up jitter lands in the wall clock the
                # rate is divided by, while each request's own latency is timed
                # by the request and is not affected. So the pattern keeps its
                # tail and gives up its rate, rather than publishing a number
                # that would sit on the panel looking like a measurement.
                "queued_rate_unmeasured": (
                    "a rate over a pass this short is dominated by the lanes starting, "
                    "so its spread exceeded its own value — the tail is reported instead"
                ),
                "queued_read_iops_observed": round(
                    statistics.median(series["queued_read_iops_observed"]), 1
                ),
                "queued_write_iops_observed": round(
                    statistics.median(series["queued_write_iops_observed"]), 1
                ),
                "directory": str(self.directory),
                # By `UniqueId`, so a reader can tell two runs on two drives
                # apart — and so a run carried to another machine is visibly
                # about a different drive (C5).
                "physical_disk": self.physical_disk(),
                "cache_bypassed": True,
            },
            duration_seconds=time.perf_counter() - started,
        )
