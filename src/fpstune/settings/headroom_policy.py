"""What a measured band and a measured bottleneck are allowed to change.

`performance_headroom` answers two questions — how much of its target a machine
reaches, and which side the frame waited on — and until now only the top band did
any work. `critical`, `short` and `near` were the same to the engine, and the
bottleneck reached the user's screen and moved nothing. A measurement nothing
acts on is a number, not a decision.

Three rules, and each is the product's own consequence 5 read back:

**At target, the quality-leaning value is the right one.** D1b lowered eleven
MW4 recommendations to their frames-first tier because this machine measures 19%
of its target. That was the correct static answer, and it stays the static
answer — but a machine that *does* hold its target has frames going unused, and
spending them on the channel that carries information is what the ceiling means.
So `met` raises the value as well as promoting the scope.

**Below target, a frame the user did not ask for is worth more than a tier they
did not notice.** `short` and `critical` pull the frame-buying settings out of
`complete` — where they sit behind an opt-in — into `recommended`. Nothing about
their *value* changes; what changes is whether the user has to go looking.

**The bottleneck decides which of those settings is worth anything.** An upscaler
tier is GPU-side; particle count and world streaming are CPU-side. On a machine
whose CPU is the wall, dropping the upscaler tier buys nothing and costs image
quality, so it stays opt-in. Below half the target both sides are spent
regardless — at 19% of a 300 Hz panel there is no side that has room.

`near` is deliberately empty. A machine at 90% needs the small savings it already
has recommended; re-scoping settings there would spend image quality for frames
it does not need.
"""

from __future__ import annotations

from dataclasses import dataclass

from fpstune.settings.performance_headroom import (
    TIER_CRITICAL,
    TIER_MET,
    TIER_SHORT,
)

__all__ = ["BandRule", "GAME_RULES", "quality_value", "rules_for", "should_promote"]

#: Which side of the frame a setting buys back. `gpu` and `cpu` are the two the
#: measurement can distinguish; a setting that helps either way carries `None`.
SIDE_GPU = "gpu"
SIDE_CPU = "cpu"


@dataclass(frozen=True)
class BandRule:
    """What one setting does when the measurement says something.

    Attributes:
        setting_id: Full setting id the rule applies to.
        quality_when_met: The value to recommend on a machine at its target, or
            `None` where the frames-first value is already the right one at any
            band. Must be one of the setting's own choices — enforced by test.
        side: Which side of the frame this setting buys back (`gpu`, `cpu`), or
            `None` when it buys on both.
        promote_when_short: Whether falling below target moves this setting out
            of `complete` into `recommended`. Only meaningful for a setting that
            is in `complete` and whose recommendation *gains* frames.
    """

    setting_id: str
    quality_when_met: str | None = None
    side: str | None = None
    promote_when_short: bool = False


# MW4. Every `quality_when_met` here is the value D1b lowered *from*, so this is
# not a new opinion about image quality — it is the same one, restored on the
# machine that can afford it.
_MW4_RULES: tuple[BandRule, ...] = (
    # Upscalers: the tier is bought with GPU time, so a CPU-bound machine gains
    # nothing by dropping it and loses the image quality anyway.
    BandRule("game_config:mw4:dlss_perf_mode", "Maximum Quality", SIDE_GPU, True),
    BandRule("game_config:mw4:amd_fsr_quality", "Maximum Quality", SIDE_GPU, True),
    BandRule("game_config:mw4:amd_fsr1_quality", "Maximum Quality", SIDE_GPU, True),
    BandRule("game_config:mw4:xess_quality", "Ultra Quality", SIDE_GPU, True),
    # Texture tier is a VRAM/bandwidth decision — GPU side, and the 1% low is
    # where an 8 GB card shows it.
    BandRule("game_config:mw4:texture_quality", "0", SIDE_GPU, True),
    # Shading and filtering: GPU work, and none of them is in `complete`, so the
    # band only decides their value.
    BandRule("game_config:mw4:shadow_quality", "Medium", SIDE_GPU),
    BandRule("game_config:mw4:anisotropic", "aniso 16x", SIDE_GPU),
    BandRule("game_config:mw4:dlss_model", "TRANSFORMER", SIDE_GPU),
    BandRule("game_config:mw4:model_quality", "High Quality", SIDE_GPU),
    # CPU side: particle simulation and streaming are submitted by the CPU, so
    # these are the channels a CPU-bound machine is actually spending.
    #
    # Neither promotes, and nothing else on this side does either: every MW4
    # setting sitting in `complete` that a CPU-bound machine could give up costs
    # the player information. `marks_player_only` is the clearest — hiding other
    # players' bullet marks removes where a shot came from — so it stays opt-in at
    # every band, which is what `test_performance_headroom` has always said. The
    # honest consequence is that on a CPU-bound machine the bottleneck's effect is
    # to *withhold* the GPU-side promotions, not to offer a CPU-side trade.
    BandRule("game_config:mw4:particle_quality", "medium", SIDE_CPU),
    BandRule("game_config:mw4:world_streaming", "High", SIDE_CPU),
)

# MW3, from the same D1b pass. Fewer settings, same rule — the mechanism is per
# game because a machine that holds 300 fps in one title holds 60 in another.
#
# None of these promotes: all three already sit in `recommended`, so a band could
# only move their value. `dlss_rr_perf_mode` is deliberately absent — D1b put it
# back to the game's own default on a build where ray tracing is recommended off,
# and a ray-reconstruction tier on a machine not tracing rays is not a quality
# raise, it is a setting with nothing to act on.
_MW3_RULES: tuple[BandRule, ...] = (
    BandRule("game_config:mw3:dlss_perf_mode", "Maximum Quality", SIDE_GPU),
    BandRule("game_config:mw3:screen_space_shadows", "High", SIDE_GPU),
)

GAME_RULES: dict[str, tuple[BandRule, ...]] = {
    "mw4": _MW4_RULES,
    "mw3": _MW3_RULES,
}


def rules_for(game: str) -> tuple[BandRule, ...]:
    """The rules for one game, empty for a game with none."""
    return GAME_RULES.get(game, ())


def should_promote(rule: BandRule, tier: str, bottleneck: str) -> bool:
    """Whether this setting leaves `complete` at this band and bottleneck.

    Args:
        rule: The setting's rule.
        tier: `met` / `near` / `short` / `critical` / `unknown`.
        bottleneck: `gpu` / `cpu` / `both` / `unknown`.

    Returns:
        True when the setting should be recommended rather than offered.
    """
    if not rule.promote_when_short:
        return False
    if tier == TIER_CRITICAL:
        # Below half the target neither side has room, so the bottleneck stops
        # being a filter: everything that buys frames is worth taking.
        return True
    if tier != TIER_SHORT:
        return False
    if rule.side is None or bottleneck in ("both", "unknown"):
        return True
    return rule.side == bottleneck


def quality_value(rule: BandRule, tier: str) -> str | None:
    """The value this band asks for, or `None` to leave the static one alone."""
    if tier != TIER_MET:
        return None
    return rule.quality_when_met
