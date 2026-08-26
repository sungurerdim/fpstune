"""Scope must mean something: ESSENTIAL is the preset users trust blindly.

The 2026-08 audit found three TCP tweaks sitting in ESSENTIAL on
``evidence_level="experimental"``. All three affect TCP only, while essentially
every modern competitive title is UDP, so the most conservative preset was
applying tweaks that did nothing for games and cost download throughput.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import SettingScope
from fpstune.settings.registry import SettingsRegistry

DEMOTED_TCP_TWEAKS = [
    "network:nagle_algorithm",
    "network:tcp_ack_frequency",
    "network:tcp_del_ack_ticks",
]


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    return SettingsRegistry(discover_dynamic=False)


def test_essential_scope_carries_no_experimental_evidence(registry: SettingsRegistry) -> None:
    offenders = [
        s.id
        for s in registry.get_all()
        if s.scope is SettingScope.ESSENTIAL and s.evidence_level == "experimental"
    ]
    assert offenders == [], (
        "ESSENTIAL is the preset applied by users who do not read per-setting "
        f"evidence. Unproven tweaks belong in COMPLETE. Offenders: {offenders}"
    )


@pytest.mark.parametrize("setting_id", DEMOTED_TCP_TWEAKS)
def test_tcp_tweaks_stay_out_of_essential(registry: SettingsRegistry, setting_id: str) -> None:
    setting = registry.get(setting_id)
    assert setting is not None
    assert setting.scope is not SettingScope.ESSENTIAL


@pytest.mark.parametrize("setting_id", DEMOTED_TCP_TWEAKS)
def test_tcp_tweaks_warn_about_their_real_cost(registry: SettingsRegistry, setting_id: str) -> None:
    # These are not free: forcing acknowledgements burns upstream bandwidth.
    # A user enabling them deserves to see that, not just a latency promise.
    setting = registry.get(setting_id)
    assert setting is not None
    assert setting.risk_warning
    assert "throughput" in setting.risk_warning.lower()


@pytest.mark.parametrize("setting_id", DEMOTED_TCP_TWEAKS)
def test_tcp_tweaks_are_not_written_at_all(registry: SettingsRegistry, setting_id: str) -> None:
    """fpstune must recommend the Windows default for these, not the tweak.

    Stronger than the `risk_level == "advanced"` this replaces. That assertion
    made sense while the settings still recommended writing the keys, and it
    described the cost of following the recommendation. The recommendation is now
    the default, so the recommended action is the safe one and `advanced` would
    be describing a direction fpstune no longer points in.

    Every one of these carried a risk_warning ending in "delete the value to
    restore Windows behaviour" while `recommended_value` told fpstune to write
    it — the copy and the action disagreed, and the action won on every machine
    that ran a bulk apply. Nagle and delayed-ACK tuning touches TCP only, modern
    competitive titles are UDP, TCP titles that care set TCP_NODELAY themselves
    (which overrides the registry key), and forcing acknowledgements costs
    download throughput. Applying the recommendation now removes the keys.
    """
    setting = registry.get(setting_id)
    assert setting is not None
    assert setting.recommended_value == setting.default_value, (
        f"{setting_id} recommends writing a key its own risk_warning tells users to delete"
    )


@pytest.mark.parametrize("setting_id", DEMOTED_TCP_TWEAKS)
def test_tcp_tweaks_do_not_promise_udp_gains(registry: SettingsRegistry, setting_id: str) -> None:
    # The old impact_scores claimed a flat latency win with no qualifier, which
    # read as universal. The benefit is TCP-only and must say so.
    setting = registry.get(setting_id)
    assert setting is not None
    latency = str(setting.impact_scores.get("latency_ms", ""))
    assert "TCP" in latency, f"{setting_id} still advertises an unqualified latency gain"


def test_essential_stays_small(registry: SettingsRegistry) -> None:
    """ESSENTIAL is what the conservative preset applies, so it growing unnoticed
    is how unproven tweaks reach cautious users.

    Counted as *one machine would see it*, which is the only number that means
    anything here. A vendor-gated setting is invisible on the other two vendors,
    so `nvidia_reflex`, `amd_antilag` and `intel_xell` are three entries in the
    registry and exactly one applied tweak on any real card — counting all three
    would inflate the preset by settings that machine can never run.

    Not measured against a live registry: that would make the answer depend on
    the developer's monitor and GPU, which is the machine-specific dependency
    C9 exists to keep out of the source.
    """
    essential = [s for s in registry.get_all() if s.scope is SettingScope.ESSENTIAL]

    vendor_neutral = [s for s in essential if "gpu_vendor" not in s.applicable_conditions]
    by_vendor: dict[str, list[str]] = {}
    for s in essential:
        vendor = s.applicable_conditions.get("gpu_vendor")
        if vendor:
            by_vendor.setdefault(vendor, []).append(s.id)

    # The worst case any single machine faces: everything ungated, plus whichever
    # vendor contributes most.
    worst_case = len(vendor_neutral) + max((len(v) for v in by_vendor.values()), default=0)
    assert worst_case <= 20, {
        "neutral": [s.id for s in vendor_neutral],
        "per_vendor": by_vendor,
    }


def test_derived_settings_declare_their_scope_deliberately() -> None:
    """The static count above cannot see settings built from hardware.

    They are checked here by calling the factories directly, with values passed
    in, so the answer is the same on every machine. Each game contributes at most
    one derived ESSENTIAL — its in-game frame cap — and a second would mean the
    conservative preset grows every time a game is added.
    """
    from fpstune.settings.definitions.game_configs_mw4 import (
        create_mw4_aa_technique_setting,
        create_mw4_fps_cap_setting,
        create_mw4_menu_fps_cap_setting,
        create_mw4_refresh_rate_setting,
        create_mw4_resolution_setting,
        create_mw4_vram_scale_setting,
    )

    derived = [
        create_mw4_fps_cap_setting(240),
        create_mw4_menu_fps_cap_setting(240),
        create_mw4_refresh_rate_setting(240),
        create_mw4_resolution_setting(2560, 1440),
        create_mw4_vram_scale_setting(8192),
        create_mw4_aa_technique_setting("nvidia"),
    ]

    essential = [s.id for s in derived if s.scope is SettingScope.ESSENTIAL]
    assert essential == ["game_config:mw4:fps_cap_ingame"], essential


def test_every_scope_bucket_is_populated(registry: SettingsRegistry) -> None:
    # A scope with zero members means the selector silently does nothing.
    for scope in (SettingScope.ESSENTIAL, SettingScope.RECOMMENDED, SettingScope.COMPLETE):
        assert [s for s in registry.get_all() if s.scope is scope], f"{scope} is empty"


def test_no_setting_writes_a_command_cs2_removed(registry: SettingsRegistry) -> None:
    """CS2 dropped the Source 1 audio tuning commands when it moved to Source 2.

    `snd_mixahead` and friends answer "unknown command"; a dead line in an
    autoexec is simply ignored. fpstune shipped `snd_mixahead 0.05` and claimed
    12 ms for it, and reported success because detection only looked for its own
    marker in the file rather than anything the game acts on — so the setting
    could never disagree with itself.

    Several "CS2 commands" lists still circulating are recycled CS:GO configs,
    which is exactly how this gets re-added by someone acting in good faith.
    """
    removed_in_source2 = (
        "snd_mixahead",
        "snd_mix_async",
        "snd_headphone_pan_exponent",
        "snd_front_headphone_position",
        "snd_rear_headphone_position",
    )
    offenders = [
        (s.id, cvar)
        for s in registry.get_all()
        if s.id.startswith("game_config:cs2:")
        for cvar in removed_in_source2
        if cvar in s.apply_command or cvar in str(s.apply_args)
    ]
    assert offenders == [], f"writing a command CS2 does not have: {offenders}"


def test_no_setting_reports_the_swept_latency_cap(registry: SettingsRegistry) -> None:
    """-12.0 was a clipped sweep value, never a measurement.

    Eleven settings carried it identically, which is the signature of a cap
    rather than of eleven independent findings. Each was triaged: five had no
    latency mechanism at all and went to 0.0, one wrote a command CS2 does not
    have and was removed, one described jitter and now says so. The three that
    remain state a range in their own copy that -12 falls inside.
    """
    offenders = [
        s.id
        for s in registry.get_all()
        if s.impact_scores.get("latency_ms") in (-12.0, -12)
        # These three pair it with copy stating a range that contains it.
        and s.id
        not in {
            "gpu-amd:vsync",
            "game_config:mw3:dlss_frame_generation",
            "game_config:mw3:fsr_frame_interpolation",
        }
    ]
    assert offenders == [], f"still advertising the swept cap as a measurement: {offenders}"
