"""The bulk planner: what may run together, decided from the settings' own declarations."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fpstune.settings.base import SettingCategory, SettingExecutor
from fpstune.settings.bulk_plan import (
    BulkPlanError,
    plan_lanes,
    run_lanes,
    validate_declarations,
)


def _setting(setting_id: str, **kwargs) -> SettingExecutor:
    return SettingExecutor(
        id=setting_id,
        category=SettingCategory.NETWORK,
        display_name=setting_id.rsplit(":", 1)[-1].replace("_", " ").title(),
        description="A setting.",
        choices=("a", "b"),
        default_value="a",
        recommended_value="b",
        **kwargs,
    )


def _ids(lanes: list[list[SettingExecutor]]) -> list[list[str]]:
    return [[s.id for s in lane] for lane in lanes]


class TestResourceKey:
    def test_an_adapter_setting_is_keyed_by_the_ifindex_it_writes(self) -> None:
        a = _setting("network:wifi:power_management", apply_args={"ifindex": 7})
        b = _setting("network:wifi:wake_on_lan", apply_args={"ifindex": 7, "restart_adapter": True})

        assert a.resource_key == b.resource_key == "adapter:7"

    def test_two_adapters_have_two_keys(self) -> None:
        a = _setting("network:wifi:power_management", apply_args={"ifindex": 7})
        b = _setting("network:eth:power_management", apply_args={"ifindex": 9})

        assert a.resource_key != b.resource_key

    def test_a_declared_resource_wins_and_a_machine_wide_setting_has_none(self) -> None:
        assert _setting("network:dns_security", resource="dns").resource_key == "dns"
        assert _setting("network:tcp_nagle").resource_key is None

    def test_a_setting_cannot_apply_after_itself(self) -> None:
        with pytest.raises(ValueError, match="after itself"):
            _setting("network:loop", apply_after=("network:loop",))


class TestPlanLanes:
    def test_unrelated_settings_each_get_their_own_lane_in_client_order(self) -> None:
        settings = [_setting("core:c"), _setting("core:a"), _setting("core:b")]

        assert _ids(plan_lanes(settings)) == [["core:c"], ["core:a"], ["core:b"]]

    def test_same_adapter_settings_share_a_lane_in_client_order(self) -> None:
        power = _setting("network:wifi:power_management", apply_args={"ifindex": 7})
        other = _setting("core:other")
        wol = _setting("network:wifi:wake_on_lan", apply_args={"ifindex": 7})

        assert _ids(plan_lanes([power, other, wol])) == [
            ["network:wifi:power_management", "network:wifi:wake_on_lan"],
            ["core:other"],
        ]

    def test_a_dependency_moves_ahead_of_its_dependent_whatever_the_client_order(self) -> None:
        security = _setting("network:dns_security", resource="dns")
        doh = _setting(
            "network:dns_over_https", resource="dns", apply_after=("network:dns_security",)
        )

        assert _ids(plan_lanes([doh, security])) == [
            ["network:dns_security", "network:dns_over_https"]
        ]

    def test_an_ordering_alone_joins_settings_that_share_no_resource(self) -> None:
        first = _setting("core:first")
        second = _setting("core:second", apply_after=("core:first",))

        assert _ids(plan_lanes([second, first])) == [["core:first", "core:second"]]

    def test_a_dependency_missing_from_the_run_is_not_waited_for(self) -> None:
        doh = _setting("network:dns_over_https", apply_after=("network:dns_security",))
        other = _setting("core:other")

        assert _ids(plan_lanes([doh, other])) == [["network:dns_over_https"], ["core:other"]]

    def test_a_chain_through_a_middle_setting_is_one_lane(self) -> None:
        a = _setting("core:a")
        b = _setting("core:b", apply_after=("core:a",), resource="x")
        c = _setting("core:c", resource="x")

        # c and b share a resource, b follows a: one lane, client order kept
        # wherever no dependency decides it, and a still ahead of b.
        assert _ids(plan_lanes([c, b, a])) == [["core:c", "core:a", "core:b"]]

    def test_a_cycle_in_the_run_is_refused_not_scheduled(self) -> None:
        a = _setting("core:a", apply_after=("core:b",))
        b = _setting("core:b", apply_after=("core:a",))

        with pytest.raises(BulkPlanError, match="core:a"):
            plan_lanes([a, b])

    def test_an_empty_run_has_no_lanes(self) -> None:
        assert plan_lanes([]) == []


class TestValidateDeclarations:
    def test_an_unknown_apply_after_id_is_refused_naming_both_rows(self) -> None:
        doh = _setting("network:dns_over_https", apply_after=("network:dns_secruity",))

        with pytest.raises(BulkPlanError, match=r"network:dns_over_https.*dns_secruity"):
            validate_declarations([doh, _setting("network:dns_security")])

    def test_a_cycle_is_refused(self) -> None:
        a = _setting("core:a", apply_after=("core:c",))
        b = _setting("core:b", apply_after=("core:a",))
        c = _setting("core:c", apply_after=("core:b",))

        with pytest.raises(BulkPlanError, match="cycle"):
            validate_declarations([a, b, c])

    def test_a_valid_chain_passes(self) -> None:
        validate_declarations(
            [
                _setting("core:a"),
                _setting("core:b", apply_after=("core:a",)),
                _setting("core:c", apply_after=("core:a", "core:b")),
            ]
        )


class TestRegistryBuildValidates:
    def test_a_registry_with_a_bad_declaration_does_not_build(self) -> None:
        from fpstune.settings.registry import SettingsRegistry

        bad = [_setting("core:a", apply_after=("core:nowhere",))]
        with (
            patch("fpstune.settings.definitions.get_all_static_settings", return_value=bad),
            pytest.raises(BulkPlanError, match="core:nowhere"),
        ):
            SettingsRegistry(discover_dynamic=False)

    def test_the_shipped_definitions_validate(self) -> None:
        from fpstune.settings.registry import SettingsRegistry

        registry = SettingsRegistry(discover_dynamic=False)
        validate_declarations(registry.get_all())


class TestShippedDeclarations:
    def test_dns_over_https_waits_for_dns_security_and_shares_its_resource(self) -> None:
        from fpstune.settings.registry import SettingsRegistry

        registry = SettingsRegistry(discover_dynamic=False)
        security = registry.get("network:dns_security")
        doh = registry.get("network:dns_over_https")
        assert security is not None and doh is not None

        assert doh.apply_after == ("network:dns_security",)
        assert security.resource_key == doh.resource_key == "dns"
        assert _ids(plan_lanes([doh, security])) == [
            ["network:dns_security", "network:dns_over_https"]
        ]


class TestRunLanes:
    def test_a_raising_setting_is_reported_and_its_lane_goes_on(self) -> None:
        a = _setting("network:wifi:power_management", apply_args={"ifindex": 7})
        b = _setting("network:wifi:wake_on_lan", apply_args={"ifindex": 7})
        c = _setting("core:other")

        def run_one(setting: SettingExecutor) -> str:
            if setting is a:
                raise RuntimeError("adapter vanished")
            return f"ran {setting.id}"

        finished = run_lanes(plan_lanes([a, b, c]), run_one, max_workers=4)
        outcomes = {setting.id: outcome for setting, outcome in finished}

        assert isinstance(outcomes[a.id], RuntimeError)
        assert outcomes[b.id] == f"ran {b.id}"
        assert outcomes[c.id] == f"ran {c.id}"

    def test_no_lanes_is_no_outcomes(self) -> None:
        assert run_lanes([], lambda s: s, max_workers=4) == []
