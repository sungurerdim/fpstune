"""Which claims this build can check, which it cannot, and why.

`verify_round` knows how to judge a claim once someone hands it a measurement.
This module answers the question that comes before that one: for the settings a
user is about to apply, what could we actually measure, and with what?

It exists because the interesting number is the second one. A tool that reports
"4 of 4 claims verified" after silently discarding the fifty-six it had no way to
measure has said something false with true arithmetic. So the mapping below is
deliberately small and every gap in it is named rather than hidden — `coverage()`
returns the unmeasurable claims alongside the measurable ones, each with the
reason it could not be checked.

Four kinds of gap, and they are genuinely different:

*Not the kind of claim a benchmark adjudicates.* `{"privacy": "improved"}` is a
statement about what leaves the machine; `{"footstep_clarity": "improved"}` is
about what a player can hear. No instrument settles either, and no instrument
ever will. This is the largest group by far — 100 of the 150 claims that state
no number — and until it had a name, every one of them read as "somebody forgot
to write a number", which is a to-do list that can never be finished.

*No number in the claim.* `{"stutter_reduction": "significant"}` is about
something an instrument could measure, written in a form that cannot be
compared. That one *is* a to-do: the number exists, it just was not written.

*No direction.* An idle frame cap states a ceiling — "90" — which cannot be
scored as a gain in either direction. The setting still works; the number is
just not the kind you compare.

*No instrument.* `fps_gpu_bound` is a perfectly measurable quantity that nothing
in this build separates from `fps`. That one is a to-do, not a fact about the
setting, and it should read as a to-do.

The order those are checked in is the whole point. Ask "did somebody forget a
number" first and a privacy claim answers yes, joining a queue it can never
leave.

The field names below are the keys each benchmark's own ``to_dict()`` emits, and
a test asserts they still exist — a rename in `presentmon.py` would otherwise
turn into a claim that silently stopped being checkable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fpstune.benchmark.verify_round import Claim, claims_of, direction_of


@dataclass(frozen=True)
class Source:
    """One instrument, and the claim metrics it can speak to."""

    name: str
    """Module under `fpstune.benchmark` that produces it."""

    requires: str
    """What has to be true for this to produce a reading, in a user's words."""

    fields: dict[str, str]
    """Claim metric -> the key that metric comes from in the tool's ``to_dict()``."""

    units: dict[str, str] = field(default_factory=dict)
    """Display unit per claim metric, where one reads better than none."""


# Only mappings where the two quantities are genuinely the same thing. The
# temptation is to map loosely so the coverage number looks better, and a loose
# mapping produces a verdict that reads as evidence while comparing two different
# quantities — worse than reporting no verdict at all.
SOURCES: tuple[Source, ...] = (
    Source(
        name="presentmon",
        requires="a game running and rendering frames",
        fields={
            "fps": "fps_avg",
            "fps_1_percent_low": "fps_1_percent_low",
            "frame_time_ms": "frametime_avg",
            "stutter_count": "stutter_count",
        },
        units={"frame_time_ms": "ms"},
    ),
    Source(
        name="network",
        requires="a reachable host to measure against",
        fields={
            "latency_ms": "ping_avg",
            "jitter_ms": "jitter_avg",
            "packet_loss": "ping_loss_percent",
        },
        units={"latency_ms": "ms", "jitter_ms": "ms", "packet_loss": "%"},
    ),
    Source(
        name="furmark",
        requires="a GPU load run, which heats the card on purpose",
        fields={
            "gpu_temp_c": "gpu_temp_max",
            "power_watts": "gpu_power_max",
        },
        units={"gpu_temp_c": "C", "power_watts": "W"},
    ),
    Source(
        name="dpc",
        requires="nothing — it measures the machine as it is",
        fields={
            # The timer's own jitter, which is what a latency spike is made of.
            # Deliberately not mapped to `latency_ms`: this is variation in when
            # a thread wakes, not how long a round trip takes, and conflating
            # them would let a network claim be "verified" by a timer.
            "latency_spike_ms": "timing_jitter_max_us",
        },
        units={"latency_spike_ms": "ms"},
    ),
    Source(
        name="disk_io",
        requires="room for a temporary file on the drive holding your temp directory",
        fields={
            "storage_performance": "storage_performance",
            # Sequential throughput is what a loading screen waits on, so the
            # claim about load times is answered by the same reading.
            "loading_speed": "storage_performance",
        },
        units={"storage_performance": "MB/s", "loading_speed": "MB/s"},
    ),
    Source(
        name="network_load",
        requires="an internet connection this may download about 25 MB over",
        fields={
            # One reading, three claim spellings. Settings say `throughput`,
            # `download_throughput` and `bandwidth` for the same quantity, and
            # mapping all three to the one measurement is honest where inventing
            # three separate ones would not be.
            "download_throughput": "download_throughput",
            "throughput": "download_throughput",
            "bandwidth": "download_throughput",
        },
        units={
            "download_throughput": "Mbps",
            "throughput": "Mbps",
            "bandwidth": "Mbps",
        },
    ),
    Source(
        name="memory",
        requires="nothing — it allocates its own working set",
        fields={"memory_bandwidth": "memory_bandwidth"},
        units={"memory_bandwidth": "MB/s"},
    ),
)

# Metrics no benchmark adjudicates, and none ever will — each with what kind of
# claim it actually is.
#
# These are not gaps. A gap is something an instrument could close, and closing
# any of these would mean building an instrument for "is the player able to tell
# where that sound came from". They are real claims, they are why several
# settings exist, and the only wrong thing that can be done with them is to file
# them beside `fps_gpu_bound` on a list headed "not measured yet".
#
# The bar for adding one is that no measurement could settle it *in principle*.
# "Nothing here measures it" is `NO_INSTRUMENT`; "it takes years" is
# `NO_INSTRUMENT` too. This list is only for questions that are not the kind a
# stopwatch answers.
NOT_JUDGEABLE: dict[str, str] = {
    "privacy": "what leaves the machine, which is a question about data and not about speed",
    "security": "what an attacker could reach, which no timing run establishes",
    "system_integrity": "whether the system is intact, which is a state and not a rate",
    "system_control": "whether the user decides something Windows otherwise decides",
    "driver_stability": "whether a driver misbehaves over weeks, not inside a round",
    "target_visibility": "whether an opponent can be told from the scenery",
    "target_clarity": "whether a shape at range resolves into something identifiable",
    "footstep_clarity": "whether a player can tell where a sound came from",
    "ability_readability": "whether an effect announces what it is",
    "visual_quality": "how the image looks, which is the player's judgement",
    "input_precision": "whether the aim goes where the hand went",
    "ux": "whether the thing is nicer to use",
    "interruptions": "whether the machine interrupts the player, which is a judgement",
}

# Metrics settings claim that nothing here measures yet, each with the reason.
# Listed explicitly so the gap is a decision on the record rather than an absence
# nobody notices — and so that adding an instrument means deleting a line here.
NO_INSTRUMENT: dict[str, str] = {
    "fps_gpu_bound": "nothing here separates a GPU-bound frame rate from an overall one",
    "fps_cpu_bound": "nothing here separates a CPU-bound frame rate from an overall one",
    "fps_sustained": "needs a long run under sustained load, which no benchmark here does",
    "fps_retained": "needs a long run under sustained load, which no benchmark here does",
    "cpu_usage": "no sampler for process CPU time",
    "ram_saved": "no sampler for working set",
    "ram_freed": "no sampler for working set",
    "vram_mb": "no sampler for video memory",
    "matchmaking_s": "depends on a game's servers rather than on this machine",
    "disk_freed": "measurable, but as a one-off reading rather than a before/after pair",
    "frame_time_consistency": "expressed as a quality rather than a quantity",
    "network_consistency": "expressed as a quality rather than a quantity",
    "stutter_reduction": "expressed as a quality rather than a quantity",
    "network_overhead": "no packet accounting in this build",
    "gpu_performance": "no vendor-agnostic GPU throughput number",
    "audio_attenuation_removed": "no audio path measurement",
    "battery_life": "needs hours of discharge, not a benchmark round",
    "disk_io": "no sampler for a process's disk traffic",
    # The four below are measurable in principle and not by anything that runs
    # inside a round. Listed here rather than left to be reported as "states no
    # number", because writing a number into them would change nothing: the
    # missing half is the instrument, not the figure.
    "shutdown_speed": "would need a shutdown to time, which a benchmark cannot take",
    "startup_speed": "would need a boot to time, which a benchmark cannot take",
    "crash_rate": "needs failures counted over weeks, not a benchmark round",
    "ssd_writes": "needs write volume accumulated over weeks, not a benchmark round",
    "ssd_longevity": "measured in years of endurance, which no run observes",
}

NOT_QUANTIFIED = "the claim states no number, so there is nothing to compare"
NO_DIRECTION = "the number is a ceiling rather than a gain, so it cannot move the right way"


def source_for(metric: str) -> Source | None:
    """The instrument that can measure this claim metric, if any."""
    for source in SOURCES:
        if metric in source.fields:
            return source
    return None


def why_unmeasurable(claim: Claim) -> str | None:
    """Why this claim cannot be checked here, or None if it can be.

    The order is the substance of this function.

    *Not judgeable* comes first, and it comes first for a hundred claims. Asking
    "did somebody forget a number" before "is this the kind of thing a number
    could say" files every privacy and audibility claim as an oversight, and
    puts them on a to-do list nothing can ever take them off. Checked first,
    they are named for what they are.

    *No instrument* comes next, and it comes before "no number" on purpose. Both
    are missing for `{"shutdown_speed": "faster"}`, and only one of them is the
    binding one: writing `-2s` there would not make it checkable, because
    nothing here times a shutdown. Reporting "states no number" would send
    somebody to write a number that changes nothing.

    *No number* then applies to exactly the claims where writing one is the
    whole fix — `{"throughput": "high"}` on a build that now measures
    throughput.

    *No direction* last, for the quantified claims whose number is a ceiling
    rather than a gain.
    """
    if claim.metric in NOT_JUDGEABLE:
        return NOT_JUDGEABLE[claim.metric]
    if claim.metric in NO_INSTRUMENT:
        return NO_INSTRUMENT[claim.metric]
    if not claim.is_quantified:
        return NOT_QUANTIFIED
    if direction_of(claim.metric) is None:
        return NO_DIRECTION
    if source_for(claim.metric) is None:
        return "no instrument in this build measures it"
    return None


@dataclass
class Coverage:
    """What a verification round over these settings could and could not show."""

    measurable: list[tuple[Claim, Source]] = field(default_factory=list)
    unmeasurable: list[tuple[Claim, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.measurable) + len(self.unmeasurable)

    @property
    def required_conditions(self) -> list[str]:
        """What the user would have to arrange for the measurable half to run.

        Deduplicated and ordered, so "a game running and rendering frames"
        appears once however many frame-rate claims depend on it.
        """
        seen: list[str] = []
        for _, source in self.measurable:
            if source.requires not in seen:
                seen.append(source.requires)
        return seen

    @property
    def not_judgeable(self) -> list[tuple[Claim, str]]:
        """Claims no instrument settles, and none ever will.

        Separated from the rest because they are not a shortfall. Counting them
        with the gaps produces a number that can only ever be improved by
        deleting claims that are the reason several settings exist.
        """
        return [pair for pair in self.unmeasurable if pair[0].metric in NOT_JUDGEABLE]

    @property
    def gaps(self) -> list[tuple[Claim, str]]:
        """The real shortfall: claims a measurement could settle, and does not.

        This is the list that can be worked down — by writing a number where
        somebody wrote a word, or by building the instrument.
        """
        return [pair for pair in self.unmeasurable if pair[0].metric not in NOT_JUDGEABLE]

    @property
    def summary(self) -> str:
        """Leads with the shortfall, and says which part of it is a shortfall."""
        if not self.total:
            return "These settings make no claims to check"

        qualitative = len(self.not_judgeable)
        tail = (
            f"; {qualitative} are not the kind of claim a measurement settles"
            if qualitative
            else ""
        )
        if not self.measurable:
            return f"None of the {self.total} claims can be measured on this machine{tail}"
        return (
            f"{len(self.measurable)} of {self.total} claims can be measured here; "
            f"{len(self.gaps)} are not{tail}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "total_claims": self.total,
            "measurable": [
                {
                    "setting_id": claim.setting_id,
                    "metric": claim.metric,
                    "claimed": claim.raw,
                    "source": source.name,
                    "requires": source.requires,
                }
                for claim, source in self.measurable
            ],
            "unmeasurable": [
                {
                    "setting_id": claim.setting_id,
                    "metric": claim.metric,
                    "claimed": claim.raw,
                    "reason": reason,
                    # So a reader can tell a to-do from a category. Without it,
                    # a page listing 339 unmeasurable claims reads as 339 things
                    # left undone, and a third of them are not things at all.
                    "judgeable": claim.metric not in NOT_JUDGEABLE,
                }
                for claim, reason in self.unmeasurable
            ],
            "measurable_count": len(self.measurable),
            "gap_count": len(self.gaps),
            "not_judgeable_count": len(self.not_judgeable),
            "required_conditions": self.required_conditions,
        }


def coverage(settings: list[Any]) -> Coverage:
    """Split every claim these settings make into checkable and not.

    Nothing is dropped. A claim that cannot be measured appears in the result
    with its reason, which is the difference between this and a coverage number
    that only counts its own successes.
    """
    result = Coverage()
    for setting in settings:
        for claim in claims_of(setting):
            reason = why_unmeasurable(claim)
            if reason is None:
                source = source_for(claim.metric)
                assert source is not None  # why_unmeasurable would have said so
                result.measurable.append((claim, source))
            else:
                result.unmeasurable.append((claim, reason))
    return result
