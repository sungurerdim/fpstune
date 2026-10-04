"""`cpu_min_state` is a guard, so it must follow the floor Windows publishes.

The defect: the recommendation was a literal 5. On a machine whose processor
driver publishes another Balanced floor, "apply" moved it off Windows' own
value — a tweak dressed as a guard — while reset wrote the derived default.
"""

from __future__ import annotations

from fpstune.settings.definitions.power import POWER_SETTINGS, adopt_windows_defaults


def test_recommendation_follows_the_published_default() -> None:
    setting = next(s for s in POWER_SETTINGS if s.id == "power:cpu_min_state")
    original = (setting.default_value, setting.recommended_value)
    try:
        adopt_windows_defaults([setting], reader=lambda _subgroup, _guid: 0)
        assert setting.default_value == 0
        assert setting.recommended_value == 0
    finally:
        setting.default_value, setting.recommended_value = original
