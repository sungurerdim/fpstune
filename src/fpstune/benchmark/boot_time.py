"""How long this machine's last few boots and shutdowns actually took.

`sources.py` refused `startup_speed` and `shutdown_speed` with the same sentence:
*"would need a boot to time, which a benchmark cannot take"*. True of a
benchmark, and false of Windows, which has timed every boot since Vista and
writes the result into
`Microsoft-Windows-Diagnostics-Performance/Operational` — event 100 for a boot,
event 200 for a shutdown, with the durations in the event's own data.

**Repeats are not used, deliberately.** Every other bench here measures the same
thing several times because one reading has unknown noise. Reading the same log
three times does not produce three measurements — it produces one, copied. So
the samples are the last few *boots*, which are genuinely separate measurements
of the same quantity, and a machine that has booted once has one sample and
therefore an unknown noise floor. That is the honest answer rather than three
identical numbers pretending to be a spread.

**`shutdown_speed` is closed; `startup_speed` is not.** A shutdown claim in this
registry is about Windows shutting down, which is exactly event 200. The claims
filed under `startup_speed` are mostly about a *game* starting — a shader cache,
a config that stops being rebuilt — and Windows boot time is a different
quantity. Mapping one to the other is the loose mapping `sources.py` exists to
refuse, so that gap stays on the record with its reason rewritten to say which
half exists.

**This log is restricted.** Measured on the machine this was written on:
unelevated, `Get-WinEvent -LogName ...` throws `System.UnauthorizedAccessException`
(0x80070005). The probe catches that *type* rather than its message, because the
message arrives in the system's language — the same reason every other query in
this package is keyed to ids and class names (C4's evidence carve-out).
"""

from __future__ import annotations

import time
from typing import Any

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.benchmark.win_query import query_rows
from fpstune.utils.logger import get_logger

logger = get_logger()

LOG_NAME = "Microsoft-Windows-Diagnostics-Performance/Operational"
BOOT_EVENT_ID = 100
SHUTDOWN_EVENT_ID = 200

DEFAULT_OCCURRENCES = 5
"""How many boots and shutdowns back the samples reach.

Five is a fortnight on a machine that is shut down at night and a couple of days
on one that is restarted often. Far enough back that a single slow boot after a
Windows update does not own the reading, near enough that it is about the
configuration running today.
"""

MS_PER_SECOND = 1000.0

_PER_EVENT_SECONDS = 1.0
"""What reading and parsing one event costs on a slow machine.

Each record is fetched and turned into XML, so the cost is per record rather
than per query — which is what makes the deadline grow with `occurrences`, the
only knob this bench has.
"""

_QUERY_KINDS = 2
"""Boots and shutdowns: two queries, each for `occurrences` records."""

ACCESS_DENIED = (
    "needs administrator: Windows restricts the boot diagnostics log, and this "
    "process may not read it"
)
NO_RECORDS = (
    "the boot diagnostics log holds no boot records on this machine, so there is nothing to time"
)


def build_script(occurrences: int) -> str:
    """The access probe and both queries, as one PowerShell expression.

    The probe runs first and by log name, because that is the form that reports a
    refusal as `UnauthorizedAccessException`; the filtered form answers "no
    events found" for a log it was never allowed to open, which would have this
    bench report a machine that never crashes as a machine that never boots.
    """
    count = int(occurrences)
    return (
        f"$log='{LOG_NAME}'; $access='ok'; "
        "try { $null=Get-WinEvent -LogName $log -MaxEvents 1 -ErrorAction Stop } "
        "catch [System.UnauthorizedAccessException] { $access='denied' } "
        "catch { $access='none' }; "
        "$read={param($id) if($access -ne 'ok'){ return @() }; "
        "@(Get-WinEvent -FilterHashtable @{LogName=$log;Id=$id} "
        f"-MaxEvents {count} -ErrorAction SilentlyContinue) | ForEach-Object {{ "
        "$x=[xml]$_.ToXml(); $d=@{}; "
        "foreach($n in $x.Event.EventData.Data){ $d[$n.Name]=$n.'#text' }; "
        "[pscustomobject]@{"
        "kind=[string]$id;"
        "at=[datetimeoffset]::new($_.TimeCreated).ToUnixTimeSeconds();"
        "boot_ms=$d['BootTime'];"
        "main_path_ms=$d['MainPathBootTime'];"
        "post_boot_ms=$d['BootPostBootTime'];"
        "shutdown_ms=$d['ShutdownTime']"
        "} } }; "
        "@([pscustomobject]@{kind='status';access=$access}) "
        f"+ (& $read {BOOT_EVENT_ID}) + (& $read {SHUTDOWN_EVENT_ID})"
    )


def _seconds(value: Any) -> float | None:
    """A duration in milliseconds from the event data, as seconds.

    None when the event did not carry it: an absent field and a zero-length boot
    are different, and only one of them has ever happened.
    """
    if value is None or value == "":
        return None
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return None
    if milliseconds <= 0:
        return None
    return milliseconds / MS_PER_SECOND


_access: tuple[bool, str] | None = None
"""Whether the boot log opened for this process, and the reason if not."""


def forget_access_probe() -> None:
    """Drop the cached answer. For tests, and after an elevation change."""
    global _access
    _access = None


class BootTimeBench:
    """Boot and shutdown durations, from the log Windows already keeps."""

    key = "boot_time"
    label = "Boot and shutdown"
    requires = "administrator rights, so Windows will open its boot diagnostics log"

    ignores_repeats = True
    """This bench measures once however many repeats the suite asks for.

    Declared rather than merely documented, because the suite's deadline gate
    asserts that every bench's timeout grows with the work it was configured to
    do — and for this one the work is `occurrences`, not repeats. A bench that
    quietly returned a flat deadline would be indistinguishable from one that
    forgot to derive it.
    """

    def __init__(self, *, occurrences: int = DEFAULT_OCCURRENCES) -> None:
        if occurrences < 1:
            raise ValueError("a boot reading needs at least one occurrence")
        self.occurrences = int(occurrences)

    def timeout_seconds(self, repeats: int) -> float:  # noqa: ARG002 - Bench's signature
        # Derived from the records it reads, not from the repeats it ignores:
        # two queries of `occurrences` events each, parsed one at a time. The
        # parameter stays because `Bench` declares it; see `ignores_repeats`.
        return deadline_for(_PER_EVENT_SECONDS * self.occurrences * _QUERY_KINDS, 1)

    def is_available(self) -> tuple[bool, str]:
        """Whether this process may read the log, asked once per session.

        Asked rather than assumed from `is_admin()`: the log's own permissions
        decide, and a member of Event Log Readers may open it without being an
        administrator. Refusing that machine on a privilege check would be the
        same class of mistake as a model-name allowlist — a proxy for the fact
        instead of the fact.

        Cached because an event log's permissions do not change while fpstune is
        running, and `catalogue()` asks every bench this each time a panel opens
        (C7).
        """
        global _access
        if _access is None:
            events, reason = self.read_log()
            _access = (bool(events), reason)
        return _access

    def read_log(self) -> tuple[list[dict[str, Any]], str]:
        """Every boot and shutdown record, or an empty list and the reason."""
        rows, reason = query_rows(
            build_script(self.occurrences), timeout=60, component="benchmark.boot_time"
        )
        if reason:
            return [], reason
        status = next((row for row in rows if row.get("kind") == "status"), None)
        if status is not None and status.get("access") == "denied":
            return [], ACCESS_DENIED
        events = [row for row in rows if row.get("kind") != "status"]
        if not events:
            return [], NO_RECORDS
        return events, ""

    def run(self, repeats: int) -> BenchResult:  # noqa: ARG002 - Bench's signature
        started = time.perf_counter()

        # `repeats` is deliberately unread: the samples are the last few boots,
        # and reading the same log again would copy them rather than measure.
        events, reason = self.read_log()
        if not events:
            return BenchResult(
                bench=self.key,
                label=self.label,
                ran=False,
                reason=reason,
                duration_seconds=time.perf_counter() - started,
            )

        boots = [row for row in events if str(row.get("kind")) == str(BOOT_EVENT_ID)]
        shutdowns = [row for row in events if str(row.get("kind")) == str(SHUTDOWN_EVENT_ID)]

        boot_seconds = [s for s in (_seconds(row.get("boot_ms")) for row in boots) if s is not None]
        main_path = [
            s for s in (_seconds(row.get("main_path_ms")) for row in boots) if s is not None
        ]
        shutdown_seconds = [
            s for s in (_seconds(row.get("shutdown_ms")) for row in shutdowns) if s is not None
        ]

        readings: dict[str, BenchReading] = {}
        if boot_seconds:
            readings["boot_time_s"] = BenchReading("boot_time_s", boot_seconds, "s")
        if main_path:
            # The part of the boot the user waits through, before the desktop
            # starts loading what it loads afterwards. Named separately because
            # a startup-item change moves one of these and not the other.
            readings["main_path_boot_s"] = BenchReading(
                "main_path_boot_s", main_path, "s", higher_is_better=False
            )
        if shutdown_seconds:
            readings["shutdown_time_s"] = BenchReading("shutdown_time_s", shutdown_seconds, "s")

        if not readings:
            return BenchResult(
                bench=self.key,
                label=self.label,
                ran=False,
                reason=("the boot records here carry no durations, so there is nothing to compare"),
                duration_seconds=time.perf_counter() - started,
            )

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings=readings,
            detail={
                "occurrences_requested": self.occurrences,
                "boots_read": len(boots),
                "shutdowns_read": len(shutdowns),
                # When each one was, so a reader can tell a fortnight of samples
                # from five reboots in one afternoon.
                "boot_times": [row.get("at") for row in boots],
                # Said here rather than left implicit: this bench measures once
                # however many repeats the suite asked for, because the log does
                # not change between two reads of it.
                "repeats_ignored": True,
            },
            duration_seconds=time.perf_counter() - started,
        )
