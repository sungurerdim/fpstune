r"""What Windows has recorded going wrong, counted rather than felt.

Claims in the registry are about failures — a crash rate, a driver that stops
misbehaving — and until this module there was nothing to check them against,
because a failure is not something a benchmark round produces on demand.
`sources.py` said as much: *"needs failures counted over weeks, not a benchmark
round"*. The answer to that is not a longer round. It is that Windows has been
counting for weeks already, in the System event log, and reading the count is a
measurement of exactly the thing the claim is about.

Six kinds of event, each a different failure and never blended into one score:

| Reading | Event | What it means |
|---|---|---|
| `crash_rate` | 1001 from WER, and `Minidump\*.dmp` | the machine stopped with a bug check |
| `unexpected_shutdown_count` | Kernel-Power 41 | it went down without shutting down |
| `whea_error_count` | any WHEA-Logger record | the hardware reported a fault |
| `tdr_count` | Display 4101 | the graphics driver was reset mid-frame |
| `disk_error_count` | 7, 11, 51, 129, 153 from a storage driver | a disk request failed or timed out |
| `minidump_count` | files on disk | the same crashes, counted a second way |

Three decisions worth knowing about.

*The window is a fixed trailing period, not "since the baseline".* A rate can
only be compared with another rate over a window of the same length, and the two
halves of a comparison are taken minutes apart: "since the baseline" would be
four minutes long on the after side and a week long on the before side, so one
crash would arrive as a three-hundred-fold regression. The baseline's own
timestamp is recorded in `detail` instead, which is what says whether the window
covers the change at all.

*A crash is counted twice and believed once.* The same bug check writes a WER
record and a minidump, and a machine with either one disabled under-counts. So
the crash count is the larger of the two, never their sum — adding them would
report every crash as two.

*Nothing here matches on text.* Event ids and provider ids are the same on every
Windows; the message bodies are translated, and a scan keyed to English words
would count zero on this machine and every other localised one. The one name
matched is a storage provider's registered id, which is not a message.

Deliberately not a verdict about drivers. `driver_stability` stays unjudgeable
(`sources.py`) because a fault count that has not grown says a driver has not
faulted *yet*, and time alone improves it — a metric that gets better while
nothing changes would verify any claim made about it, given a long enough wait.
The counts are a state a user can read; they are not evidence that a setting
helped.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.benchmark.win_query import query_rows
from fpstune.utils.logger import get_logger

logger = get_logger()

DEFAULT_WINDOW_DAYS = 7.0
"""How far back the scan looks, on both sides of a comparison.

A week is long enough that a machine with a real stability problem shows one and
short enough that a fault fixed a month ago is not still counted against the
configuration running today.
"""

SECONDS_PER_DAY = 86400.0

_QUERY_SECONDS = 8.0
"""What one pass over the log costs on a slow machine, per repeat.

Measured here at about two seconds for a thirty-day window across five queries;
the deadline is built on four times that, so a machine with a much larger log is
slow rather than hung.
"""

# Event ids a storage driver raises for a failed or timed-out request. Ids
# rather than text, and paired with a provider match because the System log is
# shared: id 7 belongs to a storage driver here and to something else entirely
# under another provider.
DISK_EVENT_IDS = (7, 11, 51, 129, 153)

STORAGE_PROVIDER_PATTERN = "disk|stor|nvme|ide|scsi|raid"
"""Which providers count as storage, matched against the provider id.

A provider id is the same string on every Windows — it is the name the driver
registered, not the sentence the event renders into — so this survives a
localised machine, which a message match would not.
"""

COUNT_KEYS = (
    "minidump_count",
    "bugcheck_count",
    "unexpected_shutdown_count",
    "whea_error_count",
    "tdr_count",
    "disk_error_count",
)
"""Every count this bench publishes beside the rate, in reading order."""


def build_script(since_epoch: int) -> str:
    """The whole scan as one PowerShell expression.

    Every count comes back from a single invocation: five separate ones cost
    five PowerShell start-ups, which on this machine is most of the runtime.

    `$since` is built from an integer this module computed, so nothing a caller
    typed reaches a command line.
    """
    ids = ",".join(str(event_id) for event_id in DISK_EVENT_IDS)
    since = int(since_epoch)
    return (
        f"$since=[datetimeoffset]::FromUnixTimeSeconds({since}).LocalDateTime; "
        "$count={param($h) $h['StartTime']=$since; "
        "@(Get-WinEvent -FilterHashtable $h -ErrorAction SilentlyContinue).Count}; "
        # How far back the log itself reaches. A window of seven days over a log
        # holding one is not seven days of evidence, and the rate below divides
        # by what was actually covered rather than by what was asked for.
        "$oldest=(Get-WinEvent -LogName System -Oldest -MaxEvents 1 "
        "-ErrorAction SilentlyContinue); "
        "$disk=@(Get-WinEvent -FilterHashtable "
        f"@{{LogName='System';Id={ids};StartTime=$since}} -ErrorAction SilentlyContinue "
        f"| Where-Object {{ $_.ProviderName -match '{STORAGE_PROVIDER_PATTERN}' }}); "
        "[pscustomobject]@{"
        "whea=(& $count @{LogName='System';ProviderName='Microsoft-Windows-WHEA-Logger'});"
        "bugcheck=(& $count @{LogName='System';Id=1001;"
        "ProviderName='Microsoft-Windows-WER-SystemErrorReporting'});"
        "unexpected_shutdown=(& $count @{LogName='System';Id=41;"
        "ProviderName='Microsoft-Windows-Kernel-Power'});"
        "tdr=(& $count @{LogName='System';Id=4101;ProviderName='Display'});"
        "disk_errors=$disk.Count;"
        "disk_providers=((@($disk | Select-Object -ExpandProperty ProviderName -Unique)) -join ',');"
        "log_from=$(if($oldest){[datetimeoffset]::new($oldest.TimeCreated).ToUnixTimeSeconds()}"
        "else{0})"
        "}"
    )


MINIMUM_COVERED_DAYS = 1 / 24.0
"""The shortest window a rate may be computed over, which is one hour.

A log cleared five minutes ago covers five minutes, and dividing one crash by
five minutes reports 288 crashes a day — a number produced by arithmetic rather
than by the machine. The floor bounds how wrong that can get; `covered_days` in
the detail is what says the evidence was thin.
"""


def covered_days(log_from: float, since: float, now: float, window_days: float) -> float:
    """How many days of evidence the counts actually rest on.

    The window asked for, unless the log itself begins later — a machine whose
    System log holds one day cannot answer a question about seven, and pretending
    otherwise turns a thin log into a flattering rate.
    """
    if log_from <= 0 or log_from <= since:
        return max(window_days, MINIMUM_COVERED_DAYS)
    return max((now - log_from) / SECONDS_PER_DAY, MINIMUM_COVERED_DAYS)


def minidump_count(since_epoch: float, directory: Path | None = None) -> int:
    """Crash dumps written since a moment, counted off disk.

    The directory is derived from the running system's own root rather than
    spelled out: a Windows installed on another letter keeps its dumps beside
    itself, and a hardcoded path is the machine-neutrality bug (C9) wearing a
    filename.
    """
    root = directory or Path(os.environ.get("SYSTEMROOT", "")) / "Minidump"
    if not root.is_dir():
        return 0
    seen = 0
    try:
        for dump in root.glob("*.dmp"):
            try:
                if dump.stat().st_mtime >= since_epoch:
                    seen += 1
            except OSError:
                # A dump being written while we look at it is not a reason to
                # abandon the count of the ones already there.
                continue
    except OSError as exc:
        logger.debug("Could not list crash dumps in %s: %s", root, exc)
    return seen


class EventScanBench:
    """Stability faults Windows recorded, over a fixed trailing window."""

    key = "event_scan"
    label = "Stability events"
    requires = "nothing — it reads what Windows has already recorded"

    def __init__(
        self,
        *,
        window_days: float = DEFAULT_WINDOW_DAYS,
        minidump_dir: Path | None = None,
    ) -> None:
        if window_days <= 0:
            raise ValueError("a scan window has to be a positive number of days")
        self.window_days = float(window_days)
        self._minidump_dir = minidump_dir

    def timeout_seconds(self, repeats: int) -> float:
        return deadline_for(_QUERY_SECONDS, repeats)

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def sample(self, since_epoch: float) -> tuple[dict[str, float], str]:
        """One pass: every count, or an empty result and the reason."""
        rows, reason = query_rows(
            build_script(int(since_epoch)), timeout=30, component="benchmark.event_scan"
        )
        if reason:
            return {}, reason
        if not rows:
            # The script always emits one object, so no rows at all means the
            # answer did not survive the round trip rather than that nothing
            # matched — those are different, and only one of them is a reading.
            return {}, "the event log query returned nothing at all"

        row = rows[0]
        bugcheck = float(row.get("bugcheck") or 0)
        dumps = float(minidump_count(since_epoch, self._minidump_dir))
        return (
            {
                # The larger of two counts of the same event, never the sum: one
                # bug check writes both a WER record and a dump, and a machine
                # with either one disabled would under-count on that side.
                "crash_count": max(bugcheck, dumps),
                "minidump_count": dumps,
                "bugcheck_count": bugcheck,
                "unexpected_shutdown_count": float(row.get("unexpected_shutdown") or 0),
                "whea_error_count": float(row.get("whea") or 0),
                "tdr_count": float(row.get("tdr") or 0),
                "disk_error_count": float(row.get("disk_errors") or 0),
                "log_from": float(row.get("log_from") or 0),
            },
            str(row.get("disk_providers") or ""),
        )

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()
        now = time.time()
        since = now - self.window_days * SECONDS_PER_DAY

        collected: dict[str, list[float]] = {}
        providers = ""
        for _ in range(repeats):
            sample, extra = self.sample(since)
            if not sample:
                return BenchResult(
                    bench=self.key,
                    label=self.label,
                    ran=False,
                    reason=extra,
                    duration_seconds=time.perf_counter() - started,
                )
            providers = extra or providers
            for name, value in sample.items():
                collected.setdefault(name, []).append(value)

        crashes = collected.pop("crash_count")
        log_from = max(collected.pop("log_from"))
        covered = covered_days(log_from, since, now, self.window_days)
        readings = {
            # A rate rather than a count, so a scan configured for a fortnight
            # and one configured for a week are still the same quantity — and
            # divided by the days the log actually holds, so a week-long window
            # over a one-day log does not report a crash as a seventh of one.
            "crash_rate": BenchReading(
                "crash_rate",
                [count / covered for count in crashes],
                "per day",
            )
        }
        for name in COUNT_KEYS:
            readings[name] = BenchReading(name, collected[name], "events", higher_is_better=False)

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings=readings,
            detail=self.describe_window(since, now, providers, log_from, covered),
            duration_seconds=time.perf_counter() - started,
        )

    def describe_window(
        self,
        since: float,
        now: float,
        providers: str,
        log_from: float = 0.0,
        covered: float = 0.0,
    ) -> dict[str, Any]:
        """What the counts are about, including whether they cover the change.

        `baseline_inside_window` is the one a reader needs: a trailing week that
        began before this machine's baseline was taken is counting faults from a
        configuration fpstune had not touched yet.
        """
        baseline_at = baseline_started_at()
        return {
            "window_days": self.window_days,
            "window_started_at": since,
            "window_ended_at": now,
            "storage_providers_seen": providers,
            # What the evidence really covers, which on a freshly installed or
            # recently cleared log is a fraction of the window asked for.
            "log_starts_at": log_from or None,
            "covered_days": round(covered, 4),
            "baseline_at": baseline_at,
            "baseline_inside_window": baseline_at is not None and baseline_at >= since,
        }


def baseline_started_at() -> float | None:
    """When this machine's baseline run was taken, if it has one.

    Imported inside the function: the ledger reads and writes files, and a bench
    that touched disk at import time would do it in every test that imports the
    registry.
    """
    try:
        from fpstune.benchmark import ledger

        run = ledger.baseline()
    except Exception as exc:  # noqa: BLE001 - a missing ledger is not a failed scan
        logger.debug("Could not read the baseline timestamp: %s", exc)
        return None
    return None if run is None else run.started_at
