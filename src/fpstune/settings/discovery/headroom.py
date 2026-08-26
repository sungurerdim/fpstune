"""What a measured frame rate is allowed to change about a recommendation.

Settings whose recommendation *costs* frames to buy image quality are only
tweaks on a machine already at its frame-rate ceiling; below it, the same change
lowers the ceiling. This pass is where the measurement reaches them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.probes import HardwareProbes

logger = logging.getLogger(__name__)


def apply_headroom_bands(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Let the measured band and the measured bottleneck move a setting.

    Until this existed only ``met`` did any work: ``critical``, ``short`` and
    ``near`` were identical to the engine, and the bottleneck reached the
    user's screen and changed nothing. What each band is allowed to do lives
    in ``headroom_policy`` — this pass is only the application of it, per
    game, because a machine that holds 300 fps in one title holds 60 in
    another.

    Two different changes, deliberately kept apart:

    * ``met`` **raises the value**. D1b lowered eleven MW4 recommendations to
      their frames-first tier for a machine at 19% of its target; a machine
      that holds its target has those frames going unused, and the quality
      tier is what the ceiling is for. The scope moves too, because at target
      the quality-leaning value is the recommendation rather than an offer.
    * ``short`` and ``critical`` **move the scope only**. Nothing about a
      value changes; what changes is whether a frame-buying setting sits
      behind an opt-in. Which ones move is the bottleneck's decision —
      dropping an upscaler tier on a CPU-bound machine costs image quality
      and buys nothing.

    Unmeasured changes nothing at all: a setting that costs frames has to
    earn its recommendation, and silence is not evidence.

    Returns:
        Count of settings the measurement moved. Zero is the normal answer.
    """
    from dataclasses import replace

    from fpstune.settings.applicability import values_equal
    from fpstune.settings.base import SettingScope
    from fpstune.settings.headroom_policy import (
        quality_value,
        rules_for,
        should_promote,
    )
    from fpstune.settings.performance_headroom import (
        TIER_UNKNOWN,
        read_headroom,
    )

    moved = 0
    for game in ("mw4", "mw3"):
        headroom = read_headroom(game)
        tier = headroom.tier
        if tier == TIER_UNKNOWN:
            continue

        for rule in rules_for(game):
            setting = registry.get(rule.setting_id)
            if setting is None:
                continue

            value = quality_value(rule, tier)
            promote = should_promote(rule, tier, headroom.bottleneck)
            # `met` promotes every rule it raises: at target the quality value
            # *is* the recommendation, not an offer with a cost attached.
            if value is not None:
                promote = True

            changed = False
            # Never outside the setting's own choices (C6): a file whose build
            # dropped a tier must not leave a recommendation nothing can pick.
            if value is not None and not values_equal(value, setting.recommended_value):
                if setting.choices and value not in setting.choices:
                    logger.debug(
                        "%s: %r is not in this build's choices, keeping %r",
                        rule.setting_id,
                        value,
                        setting.recommended_value,
                    )
                else:
                    setting = replace(setting, recommended_value=value)
                    changed = True
            if promote and setting.scope is not SettingScope.RECOMMENDED:
                setting = replace(setting, scope=SettingScope.RECOMMENDED)
                changed = True

            if not changed:
                continue
            registry.register(setting)
            moved += 1

        if moved:
            logger.debug(
                "%s measured %.1f fps against a %s fps target (%s, %s-bound); %d settings moved",
                game,
                headroom.measured_fps or 0.0,
                headroom.target_fps,
                tier,
                headroom.bottleneck,
                moved,
            )
    return moved
