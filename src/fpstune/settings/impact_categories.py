"""Derive what kind of gain a setting delivers from its own ``impact_scores``.

The dashboard header has always been able to say "latency tweaks", but nothing
on a row said whether that row was one. The information already existed: every
setting carries ``impact_scores``, and C2 guarantees at least one non-stability
metric in it. So the category is derived from the metric keys rather than
hand-tagged onto ~225 settings, which keeps it correct when a setting's impact
changes and removes a second place to forget to update.

``stability`` is deliberately not a category. It is not a performance metric —
C2 explicitly refuses to count it — so a "stability" tag would attach to 221 of
225 settings and mean nothing.
"""

from __future__ import annotations

from typing import Final

# Category -> the impact_scores keys that imply it. A setting can land in several.
_CATEGORY_KEYS: Final[dict[str, frozenset[str]]] = {
    "latency": frozenset(
        {
            "latency_ms",
            "jitter_ms",
            "latency_spike_ms",
            "input_precision",
            "audio_attenuation_removed",
        }
    ),
    "fps": frozenset(
        {
            "fps",
            "fps_gpu_bound",
            "fps_cpu_bound",
            "fps_1_percent_low",
            "fps_sustained",
            "fps_retained",
            "fps_cap_removed",
            "frame_time_consistency",
            "stutter_reduction",
            "gpu_performance",
            # A ceiling, like the two under "thermal" below — but not the same
            # kind, and the difference decides the category. Those two bind
            # while nobody is looking at the screen, so what they save is heat.
            # This one binds *during the match*, on battery, and what it takes
            # is the frame rate the player is in the middle of using. That is
            # consequence 3, not consequence 4.
            "fps_battery_ceiling",
        }
    ),
    "network": frozenset(
        {
            "throughput",
            "download_throughput",
            "bandwidth",
            "packet_loss",
            "network_consistency",
            "network_overhead",
            "matchmaking_s",
        }
    ),
    "resources": frozenset(
        {
            "cpu_usage",
            "ram_saved",
            "ram_freed",
            "vram_mb",
            "memory_bandwidth",
        }
    ),
    "storage": frozenset(
        {
            "disk_freed",
            "disk_io",
            "storage_performance",
            "ssd_writes",
            "ssd_longevity",
            "loading_speed",
            "startup_speed",
            "shutdown_speed",
        }
    ),
    # Heat is a performance category, not a comfort one. A GPU that spent the
    # lobby at 100% load starts the match already near its thermal limit and
    # throttles into it; one that idled through the menu starts with headroom.
    # So a cap that only binds while you are *not* playing still shows up in the
    # match, and it belongs here rather than under "fps" — it does not raise a
    # frame rate, it stops the machine spending itself on frames nobody sees.
    #
    # `fps_menu_ceiling` and `fps_unfocused_ceiling` carry the cap itself ("90",
    # "30") because that is the only honest figure: how much heat it avoids
    # depends on what the uncapped rate would have been on that GPU. The number
    # is context, the category is the claim.
    "thermal": frozenset(
        {
            "gpu_temp_c",
            "power_watts",
            "battery_life",
            "fps_menu_ceiling",
            "fps_unfocused_ceiling",
        }
    ),
    "privacy": frozenset({"privacy", "security", "system_integrity"}),
    # Consequence 5 lives here. These keys mark the settings that carry
    # information rather than polish — what the player can tell apart, and what
    # they can hear coming — which is why a setting may legitimately raise one at
    # the cost of frames. `ability_readability` is the case where an effect *is*
    # the announcement: in a MOBA a spell is recognised by its particles.
    "visual": frozenset(
        {
            "visual_quality",
            "target_visibility",
            "target_clarity",
            "footstep_clarity",
            "ability_readability",
        }
    ),
}

# Keys that are real and intentionally carry no category: they describe a
# qualitative side-effect rather than a kind of gain. Listed explicitly so the
# completeness test can tell "decided to ignore" apart from "forgot to map",
# which is the failure mode that would silently drop a tag from the UI.
IGNORED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "stability",
        "ux",
        "driver_stability",
        "system_control",
        "crash_rate",
        "interruptions",
    }
)

# Display order, most decision-relevant first. Used so two settings with the same
# categories always render them in the same order.
CATEGORY_ORDER: Final[tuple[str, ...]] = (
    "latency",
    "fps",
    # Third, ahead of network and resources, because thermal headroom is the
    # difference between a frame rate that holds and one that decays over a
    # match. Ordering it below "resources" filed it as housekeeping.
    "thermal",
    "network",
    "resources",
    "storage",
    "privacy",
    "visual",
)

ALL_CATEGORIES: Final[frozenset[str]] = frozenset(_CATEGORY_KEYS)


def derive_impact_categories(impact_scores: dict[str, str | float]) -> list[str]:
    """Return the kinds of gain these impact scores represent, in display order.

    An empty list means the setting's only metrics are qualitative ones (see
    ``IGNORED_KEYS``); it does not mean the setting is inert.
    """
    keys = set(impact_scores)
    found = {name for name, members in _CATEGORY_KEYS.items() if keys & members}
    return [c for c in CATEGORY_ORDER if c in found]


def unmapped_keys(impact_scores: dict[str, str | float]) -> set[str]:
    """Return impact keys that are neither mapped to a category nor ignored.

    A new key added to a setting would otherwise contribute no tag and give no
    signal that it was missed — the row would simply be quieter than it should be.
    """
    mapped: set[str] = set()
    for members in _CATEGORY_KEYS.values():
        mapped |= members
    return set(impact_scores) - mapped - IGNORED_KEYS
