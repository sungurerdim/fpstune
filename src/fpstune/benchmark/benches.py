"""Which benches exist, and which of them a button may start.

Kept apart from `suite.py` because every bench imports that one, and a registry
living there would import them back. This module is the only place that knows
the whole set, so a new bench is one entry here rather than a search through the
API layer and the UI.

**Not everything measurable should run because a panel offered a button**, and
the two exclusions here are the same judgement `benchmark.py` already made about
`presentmon` and `furmark`:

*A bench that spends something the user did not agree to spend* is in the
default set only when the spending is free. `network_load` moves about 33 MB a
pass, and "run everything" must not quietly mean "and use your data allowance" —
so the entry asks Windows what this connection costs (`network_load.
unmetered_connection`, over `INetworkCostManager`) and joins the default run
only on a line Windows calls unrestricted. Metered, roaming, over its limit or
unreadable all keep it out, and it is still there to be named by hand: the guard
is about what runs unasked, not about what may run.

Asked live rather than cached, because the answer changes when the user tethers
a phone — which is precisely the moment a stale "unrestricted" would be
expensive. The call costs a few milliseconds against benches measured in tens of
seconds.

*A bench that cannot answer without a condition the user has to arrange* stays
out of the runnable set entirely. `presentmon` needs a game already rendering
and would otherwise return an empty capture dressed as a measurement;
`furmark` heats the card on purpose. Both still appear in `sources.py` with
their `requires` line, so the answer is "here is what to arrange" rather than
silence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fpstune.benchmark.boot_time import BootTimeBench
from fpstune.benchmark.cpu_bench import CpuBench
from fpstune.benchmark.disk_io import DiskIoBench
from fpstune.benchmark.event_scan import EventScanBench
from fpstune.benchmark.frame_pacing import FramePacingBench
from fpstune.benchmark.gpu_memory import GpuMemoryBench
from fpstune.benchmark.memory import MemoryBench
from fpstune.benchmark.network_bench import NetworkIdleBench
from fpstune.benchmark.network_load import NetworkLoadBench, unmetered_connection
from fpstune.benchmark.pcie_link import PcieLinkBench
from fpstune.benchmark.process_sampler import ProcessSamplerBench
from fpstune.benchmark.sensors import SensorBench
from fpstune.benchmark.storage_health import StorageHealthBench
from fpstune.benchmark.suite import Bench
from fpstune.benchmark.timing_bench import TimingBench


@dataclass(frozen=True)
class Entry:
    """One bench, plus what running it costs the person who pressed the button."""

    bench: Bench
    costs: str
    """What it spends. Empty when it spends only time."""

    in_default_run: bool = True
    """Whether "run everything" includes it.

    False for anything that spends more than the machine's own time, so the
    broad button stays safe to press and the expensive one stays a choice.
    """

    @property
    def key(self) -> str:
        return self.bench.key


def _network_load_entry() -> Entry:
    """The throughput bench, and whether this line may be spent on unasked.

    The cost sentence is part of what running it costs, so it goes in `costs`
    where the panel already shows that — a user reading "this connection is on a
    fixed data allowance" beside a bench that is not in the automatic run has
    been told both the fact and the consequence in one line.
    """
    unmetered, why = unmetered_connection()
    costs = "moves about 33 MB — 25 down, 8 up"
    if not unmetered:
        costs = f"{costs}; not run automatically because {why}"
    return Entry(NetworkLoadBench(), costs=costs, in_default_run=unmetered)


def _entries() -> tuple[Entry, ...]:
    """Fresh instances per call.

    Benches hold measurement state — buffers, permutations, handles — and a
    module-level singleton would share it across two concurrent runs.
    """
    return (
        Entry(FramePacingBench(), costs=""),
        Entry(TimingBench(), costs=""),
        Entry(MemoryBench(), costs=""),
        # Works every thread for a couple of seconds, which is what measuring
        # throughput means and is nothing like a power virus: bounded, brief,
        # and the only reading that notices a core that stopped participating.
        Entry(CpuBench(), costs=""),
        Entry(DiskIoBench(), costs="writes a temporary file and deletes it afterwards"),
        Entry(NetworkIdleBench(), costs=""),
        _network_load_entry(),
        # Reads what Windows already recorded, so it costs a second of log
        # queries and nothing else. In the default run because a stability
        # regression is the one result a user most needs to see unasked.
        Entry(EventScanBench(), costs=""),
        # Reads counters the drive keeps anyway, so it writes nothing and
        # costs one query. Unelevated it reports why it cannot, which is a
        # more useful line on the panel than an absence.
        Entry(StorageHealthBench(), costs=""),
        # Spends only the seconds it sleeps between samples, and measures the
        # machine as the user leaves it — so it belongs in the run that is
        # taken unasked rather than behind a button nobody presses.
        Entry(ProcessSamplerBench(), costs=""),
        # One counter query per repeat, and it reports which adapter it read.
        Entry(GpuMemoryBench(), costs=""),
        # Reads a log Windows wrote at the last boot, so it costs one query and
        # needs no boot of its own.
        Entry(BootTimeBench(), costs=""),
        # Asks the card what link it negotiated. Cheap, and the answer is a
        # ceiling the machine set before fpstune touched anything (C1).
        Entry(PcieLinkBench(), costs=""),
        # Last in the run on purpose. It samples temperature over a few seconds,
        # and running it after the benches that do work is the closest this
        # build gets to reading the machine under the load it was measured at.
        Entry(SensorBench(), costs=""),
    )


def all_entries() -> tuple[Entry, ...]:
    return _entries()


def default_keys() -> list[str]:
    """What "run everything" means, which is not everything."""
    return [entry.key for entry in _entries() if entry.in_default_run]


def benches_for(keys: list[str] | None) -> list[Bench]:
    """The benches a caller asked for, in registry order.

    `None` means the default set rather than the whole set. An unknown key is an
    error rather than a silent skip: a caller asking for `disc_io` should be told
    it does not exist, not handed a run that quietly measured four things.
    """
    entries = _entries()
    known = {entry.key: entry for entry in entries}

    if keys is None:
        wanted = set(default_keys())
    else:
        unknown = sorted(set(keys) - set(known))
        if unknown:
            raise KeyError(f"no bench named {unknown}")
        wanted = set(keys)

    return [entry.bench for entry in entries if entry.key in wanted]


def tool_executable_names() -> list[str]:
    """The external tools a bench can leave running, by their own file names.

    Asked of the tools rather than listed here. `presentmon.py` and `furmark.py`
    each already know what their executable is called — they have to, in order
    to find it on disk after a download — so a second list in this module would
    be a copy that goes stale the next time one of them is repackaged. That is
    C9's rule about derived-not-declared applied to a process name.

    Lowercased because a Windows process name comes back in whatever case the
    image carries, and the sweep compares by equality.

    Not the suite's own benches: those are pure Python and in-process, so
    "left running from a previous session" is not a state they can be in.
    """
    names: list[str] = []

    try:
        from fpstune.benchmark.furmark import FurMarkBenchmark
        from fpstune.benchmark.presentmon import PresentMonBenchmark

        presentmon = PresentMonBenchmark()
        furmark = FurMarkBenchmark()
        candidates = [
            presentmon.presentmon_path.name,
            furmark.furmark_cli_path.name,
            furmark.furmark_path.name,
        ]
    except Exception:  # pragma: no cover - import guarded for packaging
        return []

    for name in candidates:
        lowered = name.lower()
        if lowered and lowered not in names:
            names.append(lowered)
    return names


def catalogue() -> list[dict[str, Any]]:
    """Every bench, whether it can run here, and if not why not.

    Answered before anything runs, so a user reads "start a game first" instead
    of watching a run produce nothing. This is `sources.py`'s "here is why we
    cannot check that", asked of the instruments rather than of the claims.
    """
    listing = []
    for entry in _entries():
        available, reason = entry.bench.is_available()
        listing.append(
            {
                "key": entry.key,
                "label": entry.bench.label,
                "requires": entry.bench.requires,
                "costs": entry.costs,
                "available": available,
                "reason": reason,
                "in_default_run": entry.in_default_run,
            }
        )
    return listing
