"""is_drift_guard is computed with values_equal, in one place, on the backend.

The defect this file exists for: the frontend carried its own
``String(recommended) === String(default)`` spelling of this comparison —
a second implementation of the one comparison truth (C6), and one that
disagrees on cross-type values ("0.0" vs 0). The backend now serializes the
verdict and the frontend only reads it.
"""

from __future__ import annotations

from dataclasses import replace

from fpstune.api.routes.settings import _setting_to_response
from fpstune.settings.definitions import get_all_static_settings


def _sample():
    return get_all_static_settings()[0]


class TestTheGuardVerdictIsValuesEquals:
    def test_a_cross_type_stock_value_is_still_a_guard(self) -> None:
        """values_equal coerces "0.0" == 0; the deleted String() spelling split
        them — the exact disagreement that made a second implementation a bug."""
        setting = replace(
            _sample(), default_value=0, recommended_value="0.0", is_action=False, is_readonly=False
        )
        assert _setting_to_response(setting).is_drift_guard is True
        assert str(setting.recommended_value) != str(setting.default_value)  # the old heuristic

    def test_a_real_change_is_not_a_guard(self) -> None:
        setting = replace(_sample(), default_value="enabled", recommended_value="disabled")
        assert _setting_to_response(setting).is_drift_guard is False

    def test_an_action_is_never_a_guard(self) -> None:
        setting = replace(_sample(), default_value="x", recommended_value="x", is_action=True)
        assert _setting_to_response(setting).is_drift_guard is False

    def test_the_registry_carries_the_documented_guard_population(self) -> None:
        """The ~163 recommended==default settings serialize as guards — the
        count Home stops presenting as pending changes."""
        guards = sum(1 for s in get_all_static_settings() if _setting_to_response(s).is_drift_guard)
        assert guards > 100  # a population, not an accident
