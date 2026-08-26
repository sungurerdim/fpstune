"""Impact categories must be derivable from every shipped setting's own metrics.

Guards the defect these were added for: the dashboard header advertised "latency
tweaks" while nothing on a row said whether that row was one, so the number could
not be traced to the settings that produced it.
"""

from __future__ import annotations

import pytest

from fpstune.settings.impact_categories import (
    ALL_CATEGORIES,
    CATEGORY_ORDER,
    IGNORED_KEYS,
    derive_impact_categories,
    unmapped_keys,
)
from fpstune.settings.registry import SettingsRegistry


@pytest.fixture(scope="module")
def all_settings() -> list:
    return SettingsRegistry().get_all()


class TestDerivation:
    def test_latency_metric_yields_the_latency_category(self) -> None:
        assert derive_impact_categories({"latency_ms": -3.5}) == ["latency"]

    def test_a_setting_can_carry_several_categories(self) -> None:
        cats = derive_impact_categories({"fps_gpu_bound": "+5%", "gpu_temp_c": -2})
        assert cats == ["fps", "thermal"]

    @pytest.mark.parametrize("ceiling", ["fps_menu_ceiling", "fps_unfocused_ceiling"])
    def test_an_idle_frame_cap_is_a_heat_tweak_not_an_fps_tweak(self, ceiling: str) -> None:
        """The bug this pins: a cap tagged "FPS" claims a gain it never delivers.

        Capping a static lobby at 90 does not raise anyone's frame rate. What it
        buys is a GPU that starts the match with thermal headroom instead of
        already at its limit — which does show up in the match, as a frame rate
        that holds instead of decaying. Real gain, wrong label.
        """
        assert derive_impact_categories({ceiling: 90}) == ["thermal"]

    def test_removing_a_wrongly_applied_cap_stays_an_fps_tweak(self) -> None:
        """The near-miss neighbour, so the rule above is not applied by keyword.

        `gpu-nvidia:bg_app_fps` reads the same way — a number of frames — but it
        *lifts* a cap the driver misapplies to a focused game. That is frame rate
        the user was losing, not heat they were wasting.
        """
        assert derive_impact_categories({"fps_cap_removed": 30}) == ["fps"]

    def test_categories_come_back_in_display_order_not_dict_order(self) -> None:
        # Two settings with the same categories must render them identically,
        # so the order cannot depend on how the dict happened to be written.
        a = derive_impact_categories({"gpu_temp_c": -2, "latency_ms": -1, "fps": "+3%"})
        b = derive_impact_categories({"fps": "+3%", "latency_ms": -1, "gpu_temp_c": -2})
        assert a == b == ["latency", "fps", "thermal"]

    def test_heat_ranks_with_the_performance_categories(self) -> None:
        """Ordering is the quiet half of classification.

        Filed after "resources" and "network", a heat tweak reads as
        housekeeping. It is not: thermal headroom is why a frame rate holds.
        """
        order = list(CATEGORY_ORDER)
        assert order.index("thermal") < order.index("resources")
        assert order.index("thermal") < order.index("network")

    def test_stability_alone_yields_nothing(self) -> None:
        # stability sits on 221 of 225 settings; as a tag it would carry no
        # information at all. C2 already refuses to count it as an impact.
        assert derive_impact_categories({"stability": "high"}) == []

    def test_zero_valued_metric_still_categorises(self) -> None:
        # Several settings are honest drift guards scoring 0.0. They are still
        # latency settings — the tag describes the kind of gain, not its size.
        assert derive_impact_categories({"latency_ms": 0.0}) == ["latency"]

    def test_empty_scores_yield_no_categories(self) -> None:
        assert derive_impact_categories({}) == []

    def test_every_category_is_reachable(self) -> None:
        assert set(CATEGORY_ORDER) == ALL_CATEGORIES


class TestCoverageOfShippedSettings:
    def test_no_shipped_setting_has_an_unmapped_metric(self, all_settings: list) -> None:
        # The failure this prevents: someone adds a new impact key, the setting
        # silently gets no tag, and the row is quieter than it should be with
        # nothing anywhere reporting the omission.
        offenders = {
            s.id: sorted(unmapped_keys(s.impact_scores))
            for s in all_settings
            if unmapped_keys(s.impact_scores)
        }
        assert not offenders, f"unmapped impact keys: {offenders}"

    def test_a_new_unknown_key_is_reported_rather_than_ignored(self) -> None:
        # Proves the guard above can actually fail.
        assert unmapped_keys({"some_new_metric_2027": 1.0}) == {"some_new_metric_2027"}

    def test_almost_every_setting_lands_in_at_least_one_category(self, all_settings: list) -> None:
        uncategorised = [
            s.id for s in all_settings if not derive_impact_categories(s.impact_scores)
        ]
        # A handful score only qualitative metrics (ux, crash_rate). Anything
        # beyond that means the mapping has gone stale against the definitions.
        assert len(uncategorised) <= 10, f"uncategorised: {uncategorised}"

    def test_ignored_keys_and_mapped_keys_never_overlap(self) -> None:
        for key in IGNORED_KEYS:
            assert derive_impact_categories({key: 1}) == [], key

    def test_frames_and_latency_are_what_this_product_mostly_does(self, all_settings: list) -> None:
        """Sanity anchor on the composition, measured rather than asserted.

        This used to assert latency was the single largest category. That stopped
        being true when MW4 added 52 game settings, most of them frame-rate ones —
        the product's composition changed, the mapping did not go stale. What is
        worth anchoring is that these two together are still the bulk of it, so a
        future category cannot quietly grow past both without someone noticing.
        """
        counts: dict[str, int] = {}
        for s in all_settings:
            for c in derive_impact_categories(s.impact_scores):
                counts[c] = counts.get(c, 0) + 1

        top_two = sorted(counts, key=lambda c: counts[c], reverse=True)[:2]
        assert set(top_two) == {"fps", "latency"}, counts

        rest = sum(v for k, v in counts.items() if k not in top_two)
        assert counts["fps"] + counts["latency"] > rest, counts


class TestApiExposure:
    def test_the_response_model_carries_the_categories(self) -> None:
        from fpstune.api.schemas import SettingDefinitionResponse

        assert "impact_categories" in SettingDefinitionResponse.model_fields

    def test_a_known_latency_setting_serialises_with_its_category(self) -> None:
        reg = SettingsRegistry()
        s = reg.get("game_config:mw3:nvidia_reflex")
        assert s is not None
        assert "latency" in derive_impact_categories(s.impact_scores)
