"""MW3's anti-aliasing recommendation is a property of the card, not a constant.

The defect this pins: `game_config:mw3:aa_technique` shipped as one static entry
recommending `DLSS` on every machine. An AMD or Intel card cannot run DLSS, so on
two thirds of hardware the recommendation either did nothing or left the owner on
`Filmic SMAA T2x` — a software AA path with no upscale at all, against a setting
that claims +25-35% GPU-bound frames. MW4's sibling had been derived per vendor
since it shipped; MW3's had not, and that asymmetry is exactly what C10 forbids.

Derived, so a machine whose vendor cannot be read gets no setting rather than a
recommendation about a card it does not have.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fpstune.settings.definitions.game_configs import (
    GAME_CONFIG_SETTINGS,
    create_mw3_aa_technique_setting,
)
from fpstune.settings.discovery.games_mw3 import discover_mw3_display_settings
from fpstune.settings.registry import SettingsRegistry

AA_ID = "game_config:mw3:aa_technique"


class TestTheRecommendationFollowsTheCard:
    @pytest.mark.parametrize(
        ("vendor", "expected"),
        [("nvidia", "DLSS"), ("amd", "FSR AA"), ("intel", "XeSS")],
    )
    def test_each_vendor_gets_its_own_upscaler(self, vendor: str, expected: str) -> None:
        setting = create_mw3_aa_technique_setting(vendor)
        assert setting.recommended_value == expected
        # And it is a value the game's own list allows — this picks, never invents.
        assert expected in setting.choices

    def test_the_default_stays_the_game_s_own(self) -> None:
        """`default_value` is what Windows/the game ships, never the vendor's pick.

        Reset writes this; making it vendor-specific would turn a reset into a
        second apply.
        """
        for vendor in ("nvidia", "amd", "intel"):
            assert create_mw3_aa_technique_setting(vendor).default_value == "Filmic SMAA T2x"

    def test_the_effect_names_the_card_rather_than_a_vendor(self) -> None:
        assert "amd" in create_mw3_aa_technique_setting("amd").effect


class TestNoStaticEntrySurvives:
    def test_the_static_definition_is_gone(self) -> None:
        """A static entry would be registered first and win on an unknown vendor.

        It recommended DLSS unconditionally, which is the bug. Absence is the fix:
        no vendor, no setting.
        """
        assert not any(s.id == AA_ID for s in GAME_CONFIG_SETTINGS)


class TestRegistration:
    def _registry_with_vendor(self, vendor: str | None) -> SettingsRegistry:
        gpu = MagicMock()
        gpu.vram_mb = 8192
        gpu.vendor = vendor
        registry = SettingsRegistry()
        # The constructor already ran discovery against this machine's real card,
        # so the question "what does an unreadable card get" can only be asked
        # from a clean slate.
        registry.unregister(AA_ID)
        with patch(
            "fpstune.utils.detect.get_gpu_info", return_value=None if vendor is None else gpu
        ):
            discover_mw3_display_settings(registry, registry._probes)
        return registry

    @pytest.mark.parametrize(
        ("vendor", "expected"),
        [("nvidia", "DLSS"), ("amd", "FSR AA"), ("intel", "XeSS")],
    )
    def test_discovery_registers_the_card_s_answer(self, vendor: str, expected: str) -> None:
        setting = self._registry_with_vendor(vendor).get(AA_ID)
        assert setting is not None
        assert setting.recommended_value == expected

    def test_an_unreadable_card_gets_no_setting_at_all(self) -> None:
        """Not-applicable is a first-class answer (C10); a guess is not."""
        assert self._registry_with_vendor(None).get(AA_ID) is None

    def test_an_unknown_vendor_gets_no_setting_either(self) -> None:
        assert self._registry_with_vendor("qualcomm").get(AA_ID) is None
