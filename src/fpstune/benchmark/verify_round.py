"""Check what a setting claimed against what the machine actually did.

Every setting carries an ``impact_scores`` claim — ``{"fps": "+3-5%"}``,
``{"latency_ms": -15.0}``. Those numbers came from vendor documentation, from
community benchmarks, from one person's machine. None of them came from *your*
machine, and until this module existed nothing ever compared them to it. A tool
whose whole argument is "measure, do not assume" was asking users to take its
own headline numbers on faith.

So: measure, apply, measure again, and say which claims the second measurement
supports. The point is not to produce a bigger number. It is to be able to
answer "did this actually do anything here" with something other than a shrug —
including, and especially, when the answer is no.

**Three things this refuses to do**, because each is how a measurement turns
into marketing:

*Attribute a shared measurement to one setting.* Applying forty settings and
measuring once tells you what forty settings did together. It cannot tell you
what any one of them did, and splitting the credit forty ways would be inventing
data. A round therefore knows whether it changed one setting or many, and only
the first kind produces per-setting verdicts.

*Call noise a result.* Two runs of the same measurement on an idle machine
differ. Without knowing by how much, a 1% change is indistinguishable from
nothing happening, and reporting it as an improvement is the most flattering
mistake available. Every round measures its own noise first and refuses to call
anything smaller than that a change.

*Report "no evidence" as "no effect".* A claim about frame rate cannot be
checked without a game running. That is a limit of the measurement, not a fact
about the setting, and the two must never collapse into the same word.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# How a metric moves when things get better. A claim of "-15 ms latency" and a
# claim of "+5% fps" are both improvements; only the sign differs, and getting
# that backwards would report every success as a regression.
#
# Keys are the `impact_scores` metric names the settings actually use. Anything
# not listed here is unverifiable rather than assumed — see `direction_of`.
_LOWER_IS_BETTER: frozenset[str] = frozenset(
    {
        "latency_ms",
        "jitter_ms",
        "latency_spike_ms",
        "cpu_usage",
        "ram_usage",
        "packet_loss",
        "network_overhead",
        "matchmaking_s",
        "boot_time_s",
        "input_lag_ms",
        "frame_time_ms",
        "stutter_count",
        "dpc_latency_us",
        "vram_mb",
        "power_watts",
        "gpu_temp_c",
    }
)

_HIGHER_IS_BETTER: frozenset[str] = frozenset(
    {
        "fps",
        "fps_gpu_bound",
        "fps_cpu_bound",
        "fps_1_percent_low",
        "fps_sustained",
        "fps_retained",
        "throughput",
        "download_throughput",
        "bandwidth",
        "gpu_performance",
        "ram_saved",
        "disk_freed",
        "frame_time_consistency",
        "network_consistency",
        "stutter_reduction",
        "ram_freed",
        "memory_bandwidth",
        "storage_performance",
        "loading_speed",
        "audio_attenuation_removed",
    }
)

# Deliberately absent, and they are the interesting omissions.
#
# `fps_cap_removed`, `fps_menu_ceiling` and `fps_unfocused_ceiling` state a
# *ceiling* — "30", "90" — not a gain. Given a direction, a menu capped at 90
# would score as a 90% improvement and these would top the whole registry, which
# is why the number is left unscored.
#
# That is a statement about the number's shape and not about the setting's
# worth, and the distinction matters because it was got wrong once already: the
# two idle caps were filed under "fps", where they claimed a frame rate they
# never raise, and the correction was to file them under "thermal" — see
# `impact_categories`. What they buy is a GPU that enters the match with headroom
# instead of at its limit, and thermal headroom is exactly what decides whether a
# frame rate holds or decays. `gpu_temp_c` and `power_watts` above are directional
# for that reason: the heat itself is measurable even when the cap is not.
#
# `privacy`, `security`, `ux`, `visual_quality`, `system_integrity` and the rest
# are real claims about things a stopwatch cannot see. They stay unverifiable
# rather than being given a direction that would let a measurement pretend to
# confirm them.


class Status(StrEnum):
    """What a round is entitled to say about one claim."""

    VERIFIED = "verified"
    """Measured on this machine, moved the way the claim said, by more than noise."""

    CONTRADICTED = "contradicted"
    """Measured, and moved the *other* way by more than noise."""

    INCONCLUSIVE = "inconclusive"
    """Measured, and the change was smaller than this machine's own noise."""

    UNMEASURED = "unmeasured"
    """Nothing here could measure it. Says nothing about whether it works."""

    NOT_ATTRIBUTABLE = "not_attributable"
    """Measured, but several settings changed at once, so the credit is unassignable."""


@dataclass(frozen=True)
class Claim:
    """One ``impact_scores`` entry, parsed into something comparable."""

    setting_id: str
    metric: str
    raw: str
    low: float | None = None
    high: float | None = None
    is_percentage: bool = False

    @property
    def is_quantified(self) -> bool:
        """Whether the claim states a number at all.

        ``{"stability": "high"}`` and ``{"ux": "improved"}`` are real statements
        and are not measurable ones. C2 already refuses to let a setting carry
        only those.
        """
        return self.low is not None

    @property
    def lower_is_better(self) -> bool | None:
        return direction_of(self.metric)


def direction_of(metric: str) -> bool | None:
    """True if lower is better, False if higher is, None if unknown.

    None is a real answer and is treated as unverifiable. Guessing the direction
    of an unfamiliar metric is how a regression gets reported as a win.
    """
    if metric in _LOWER_IS_BETTER:
        return True
    if metric in _HIGHER_IS_BETTER:
        return False
    return None


_NUMBER = r"[-+]?\d+(?:\.\d+)?"


def parse_claim(setting_id: str, metric: str, raw: Any) -> Claim:
    """Turn one ``impact_scores`` value into a Claim.

    Handles the shapes the registry actually uses: ``"+3-5%"``, ``"-15%"``,
    ``"50-150MB"``, ``"4-16GB"``, ``-0.5``, ``"0%"``, ``"high"``. Anything it
    cannot read becomes an unquantified claim rather than a guessed number.
    """
    text = str(raw).strip()
    is_percentage = "%" in text

    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = float(raw)
        return Claim(setting_id, metric, text, abs(value), abs(value), is_percentage)

    # A range: "+3-5%", "50-150MB". The leading sign belongs to the whole range,
    # so "-15-20%" means "between 15 and 20 lower", not "from -15 to 20".
    ranged = re.match(rf"^\s*([-+]?)({_NUMBER.lstrip('[-+]?')})\s*-\s*({_NUMBER})", text)
    if ranged:
        low = abs(float(ranged.group(2)))
        high = abs(float(ranged.group(3)))
        return Claim(setting_id, metric, text, min(low, high), max(low, high), is_percentage)

    single = re.search(_NUMBER, text)
    if single:
        value = abs(float(single.group()))
        return Claim(setting_id, metric, text, value, value, is_percentage)

    return Claim(setting_id, metric, text, None, None, is_percentage)


def claims_of(setting: Any) -> list[Claim]:
    """Every quantifiable claim a setting makes about itself."""
    return [
        parse_claim(setting.id, metric, raw)
        for metric, raw in (setting.impact_scores or {}).items()
        # `stability` is explicitly not a performance metric (C2), so it is not
        # something a measurement could ever confirm.
        if metric != "stability"
    ]


@dataclass(frozen=True)
class Measurement:
    """One metric, measured before and after, with this machine's noise for it."""

    metric: str
    before: float
    after: float
    unit: str = ""
    noise: float = 0.0
    """The largest change this metric showed with nothing changed at all.

    Anything at or below this is indistinguishable from the machine idling.
    """

    @property
    def delta(self) -> float:
        return self.after - self.before

    @property
    def percent_change(self) -> float:
        if self.before == 0:
            return 0.0
        return (self.delta / abs(self.before)) * 100.0

    @property
    def exceeds_noise(self) -> bool:
        return abs(self.delta) > abs(self.noise)


def noise_floor(samples: list[float]) -> float:
    """How much this metric moves on its own, from repeated idle measurements.

    The spread of the samples, not their standard deviation: a claim has to beat
    what was actually observed, and two samples have no meaningful stdev anyway.
    Fewer than two samples means the noise is unknown, and unknown noise is
    treated as infinite — nothing can beat it, so nothing gets called verified
    on a single reading.
    """
    if len(samples) < 2:
        return float("inf")
    return max(samples) - min(samples)


@dataclass(frozen=True)
class Verdict:
    """What this round is entitled to say about one claim."""

    claim: Claim
    status: Status
    measurement: Measurement | None = None
    reason: str = ""

    @property
    def is_evidence(self) -> bool:
        """Whether this verdict says anything about the machine at all."""
        return self.status in (Status.VERIFIED, Status.CONTRADICTED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "setting_id": self.claim.setting_id,
            "metric": self.claim.metric,
            "claimed": self.claim.raw,
            "status": self.status.value,
            "reason": self.reason,
            "measured": None
            if self.measurement is None
            else {
                "before": self.measurement.before,
                "after": self.measurement.after,
                "delta": round(self.measurement.delta, 4),
                "percent_change": round(self.measurement.percent_change, 2),
                "unit": self.measurement.unit,
                "noise": round(self.measurement.noise, 4),
            },
        }


def judge(
    claim: Claim,
    measurement: Measurement | None,
    *,
    settings_changed: int = 1,
) -> Verdict:
    """Decide what a round may say about one claim.

    ``settings_changed`` is the number of settings applied between the two
    measurements. Above one, a measured change belongs to the whole batch and no
    single setting can be credited with it — the measurement is still reported,
    it just is not evidence *about this setting*.
    """
    if not claim.is_quantified:
        return Verdict(
            claim,
            Status.UNMEASURED,
            None,
            f"{claim.raw!r} states no number to check",
        )

    if claim.lower_is_better is None:
        return Verdict(
            claim,
            Status.UNMEASURED,
            None,
            f"nothing here knows which direction is better for {claim.metric!r}",
        )

    if measurement is None:
        return Verdict(
            claim,
            Status.UNMEASURED,
            None,
            f"this round measured nothing for {claim.metric!r}",
        )

    if settings_changed > 1:
        return Verdict(
            claim,
            Status.NOT_ATTRIBUTABLE,
            measurement,
            f"{settings_changed} settings changed between the two measurements, "
            "so this change cannot be credited to any one of them",
        )

    if not measurement.exceeds_noise:
        return Verdict(
            claim,
            Status.INCONCLUSIVE,
            measurement,
            f"changed by {measurement.delta:+.4g}{measurement.unit}, which is within "
            f"this machine's own variation of ±{measurement.noise:.4g}{measurement.unit}",
        )

    improved = measurement.delta < 0 if claim.lower_is_better else measurement.delta > 0
    if not improved:
        return Verdict(
            claim,
            Status.CONTRADICTED,
            measurement,
            f"claimed {claim.raw}, measured {measurement.percent_change:+.1f}% — "
            "the wrong way, by more than noise",
        )

    return Verdict(
        claim,
        Status.VERIFIED,
        measurement,
        f"claimed {claim.raw}, measured {measurement.percent_change:+.1f}% on this machine",
    )


@dataclass
class Round:
    """One before/apply/after cycle and everything it is entitled to conclude."""

    settings_changed: int
    verdicts: list[Verdict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def verified(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.status is Status.VERIFIED]

    @property
    def contradicted(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.status is Status.CONTRADICTED]

    @property
    def unverified(self) -> list[Verdict]:
        """Everything this round could not turn into evidence, for any reason."""
        return [v for v in self.verdicts if not v.is_evidence]

    @property
    def summary(self) -> str:
        """One sentence, and never a flattering one.

        Deliberately leads with what was *not* shown when that is most of it.
        A round that verified two claims out of sixty has not demonstrated much,
        and a summary reading "2 verified" invites the opposite conclusion.
        """
        if not self.verdicts:
            return "Nothing was checked"

        total = len(self.verdicts)
        verified = len(self.verified)
        contradicted = len(self.contradicted)

        if self.settings_changed > 1:
            return (
                f"{self.settings_changed} settings changed together, so none of the "
                f"{total} claims can be credited individually"
            )
        if contradicted:
            return f"{verified} of {total} claims verified, {contradicted} contradicted"
        if verified == 0:
            return f"None of the {total} claims could be verified on this machine"
        return f"{verified} of {total} claims verified on this machine"

    def to_dict(self) -> dict[str, Any]:
        return {
            "settings_changed": self.settings_changed,
            "summary": self.summary,
            "verified": len(self.verified),
            "contradicted": len(self.contradicted),
            "unverified": len(self.unverified),
            "verdicts": [v.to_dict() for v in self.verdicts],
            "notes": self.notes,
        }


def run_round(
    settings: list[Any],
    measurements: dict[str, Measurement],
    *,
    notes: list[str] | None = None,
) -> Round:
    """Judge every claim the given settings make against what was measured.

    ``measurements`` is keyed by metric name. A claim whose metric is absent is
    reported as unmeasured rather than dropped: "we did not check this" belongs
    in the report at least as much as "we did".
    """
    changed = len(settings)
    round_ = Round(settings_changed=changed, notes=list(notes or []))
    for setting in settings:
        for claim in claims_of(setting):
            round_.verdicts.append(
                judge(claim, measurements.get(claim.metric), settings_changed=changed)
            )
    return round_


def measure_pair(
    metric: str,
    before_samples: list[float],
    after_samples: list[float],
    unit: str = "",
) -> Measurement:
    """Build a Measurement from repeated readings on each side.

    The medians are compared, and the noise is the wider of the two sides'
    spreads — if the machine was noisier after the change than before, that is
    the noise the result has to beat.
    """
    if not before_samples or not after_samples:
        raise ValueError(f"{metric}: both sides need at least one reading")

    return Measurement(
        metric=metric,
        before=statistics.median(before_samples),
        after=statistics.median(after_samples),
        unit=unit,
        noise=max(noise_floor(before_samples), noise_floor(after_samples)),
    )
