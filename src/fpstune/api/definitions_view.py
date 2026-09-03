"""Setting definition -> API response, in one place.

The mapper lives beside neither the router nor the schema by accident: it is the
one translation from a `SettingExecutor` to what the frontend receives, and it
answers questions the schema cannot (which heading a setting renders under, what
counts as a drift guard) while the router should not have to. Moved out of
routes/settings.py when that module hit its SoC ceiling — new surface goes into a
sibling, never onto the largest file.
"""

from __future__ import annotations

from fpstune.api.schemas import SettingDefinitionResponse
from fpstune.settings.applicability import values_equal
from fpstune.settings.base import SettingExecutor
from fpstune.settings.impact_categories import derive_impact_categories


def setting_to_response(s: SettingExecutor) -> SettingDefinitionResponse:
    """Convert SettingExecutor to response model."""
    from fpstune.settings.groups import group_for

    group = group_for(s.id)

    return SettingDefinitionResponse(
        id=s.id,
        category=s.category.value,
        display_name=s.display_name,
        description=s.description,
        value_type=s.value_type.value,
        choices=list(s.choices),
        default_value=s.default_value,
        recommended_value=s.recommended_value,
        requires_reboot=s.requires_reboot,
        is_action=s.is_action,
        current_impact=s.current_impact,
        recommended_impact=s.recommended_impact,
        scope=s.scope.value,
        short_name=s.short_name,
        icon=s.icon,
        color=s.color,
        category_order=s.category_order,
        min_value=s.min_value,
        max_value=s.max_value,
        applicable_conditions=s.applicable_conditions,
        evidence_level=s.evidence_level,
        sources=s.sources,
        effect=s.effect,
        impact_scores=s.impact_scores,
        impact_categories=derive_impact_categories(s.impact_scores),
        risk_level=s.risk_level,
        risk_warning=s.risk_warning,
        perceptible_cost=s.perceptible_cost,
        is_drift_guard=(
            not s.is_action
            and not s.is_readonly
            and s.recommended_value is not None
            and s.default_value is not None
            and values_equal(s.recommended_value, s.default_value)
        ),
        # What a long action tells the user while it runs. These used to be
        # gated behind an isinstance check for a class no shipped setting used,
        # so every one of them was a constant: no duration ever reached a row,
        # and no progress pattern ever reached the stream.
        duration_estimate=s.duration_estimate,
        progress_pattern=s.progress_pattern,
        is_readonly=s.is_readonly,
        value_hints=s._derive_value_hints(),
        group_id=group.id if group else None,
        group_label=group.label if group else None,
        group_order=group.order if group else None,
    )
