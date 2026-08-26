"""Which benches exist, and which of them a button may start.

Kept apart from `suite.py` because every bench imports that one, and a registry
living there would import them back. This module is the only place that knows
the whole set, so a new bench is one entry here rather than a search through the
API layer and the UI.

**Not everything measurable should run because a panel offered a button**, and
the two exclusions here are the same judgement `benchmark.py` already made about
`presentmon` and `furmark`:

*A bench that spends something the user did not agree to spend* is not in the
default set. `network_load` downloads about 25 MB every pass, and "run
everything" should not quietly mean "and use your data". It runs when it is
named.

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

from fpstune.benchmark.disk_io import DiskIoBench
from fpstune.benchmark.frame_pacing import FramePacingBench
from fpstune.benchmark.memory import MemoryBench
from fpstune.benchmark.network_bench import NetworkIdleBench
from fpstune.benchmark.network_load import NetworkLoadBench
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


def _entries() -> tuple[Entry, ...]:
    """Fresh instances per call.

    Benches hold measurement state — buffers, permutations, handles — and a
    module-level singleton would share it across two concurrent runs.
    """
    return (
        Entry(FramePacingBench(), costs=""),
        Entry(TimingBench(), costs=""),
        Entry(MemoryBench(), costs=""),
        Entry(DiskIoBench(), costs="writes a temporary file and deletes it afterwards"),
        Entry(NetworkIdleBench(), costs=""),
        Entry(
            NetworkLoadBench(),
            costs="downloads about 25 MB",
            in_default_run=False,
        ),
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
