"""The RSS base core is derived from the machine, or the move is not offered.

The defect this file exists for: the apply command hardcoded core 2 and the
setting registered on every adapter unconditionally — on an Intel hybrid whose
topology nobody read, logical processor 2 can be an E-core, and moving NIC
receive DPCs there is a regression shipped at ``risk_level="low"``. The core is
now ``rss_target_core``'s answer, and no safe answer means no setting.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpstune.settings.definitions.network import (
    create_rss_base_processor_setting,
    rss_target_core,
)


def _cpu(*, logical: int, e_cores: int = 0, is_hybrid: bool | None = False) -> SimpleNamespace:
    return SimpleNamespace(logical_cores=logical, e_cores=e_cores, is_hybrid=is_hybrid)


class TestTheTargetIsTheMachinesAnswer:
    def test_a_classic_cpu_with_headroom_moves_to_core_2(self) -> None:
        assert rss_target_core(_cpu(logical=16)) == 2

    def test_a_hybrid_whose_p_span_covers_core_2_moves(self) -> None:
        # 6P (12 logical) + 8E: LPs 0-11 are P, so 2 is a P-core sibling.
        assert rss_target_core(_cpu(logical=20, e_cores=8, is_hybrid=True)) == 2

    def test_a_hybrid_whose_core_2_would_be_an_e_core_gets_no_move(self) -> None:
        """The gate: 1P (2 logical) + 8 E-cores — LP 2 is the first E-core."""
        assert rss_target_core(_cpu(logical=10, e_cores=8, is_hybrid=True)) is None

    def test_an_unknown_topology_gets_no_move(self) -> None:
        """Could-not-read is not permission: no real answer, no placement."""
        assert rss_target_core(_cpu(logical=16, is_hybrid=None)) is None

    def test_a_two_thread_machine_has_nowhere_better_to_go(self) -> None:
        assert rss_target_core(_cpu(logical=2)) is None

    def test_no_cpu_reading_at_all_gets_no_move(self) -> None:
        assert rss_target_core(None) is None


class TestTheCommandCarriesNoConstant:
    def test_the_apply_command_uses_the_derived_target(self) -> None:
        setting = create_rss_base_processor_setting(5, "Ethernet", 2)
        assert "%target%" in setting.apply_command
        assert setting.apply_args["target"] == 2
        assert "{ 2 }" not in setting.apply_command

    def test_the_copy_names_the_derived_core(self) -> None:
        setting = create_rss_base_processor_setting(5, "Ethernet", 2)
        assert "Core 2" in setting.recommended_impact
        assert setting.value_hints["optimized"] == "Core 2"

    def test_default_reads_the_drivers_published_default(self) -> None:
        setting = create_rss_base_processor_setting(5, "Ethernet", 2)
        assert "DefaultRegistryValue" in setting.apply_command

    def test_the_write_is_guarded_by_the_adapters_own_range(self) -> None:
        setting = create_rss_base_processor_setting(5, "Ethernet", 2)
        assert "MaxProcessorNumber" in setting.apply_command


class TestRegistrationIsGated:
    @pytest.mark.parametrize(
        ("cpu", "expected_present"),
        [
            (_cpu(logical=16), True),
            (_cpu(logical=10, e_cores=8, is_hybrid=True), False),
            (_cpu(logical=16, is_hybrid=None), False),
        ],
    )
    def test_no_safe_core_means_no_setting(
        self, monkeypatch: pytest.MonkeyPatch, cpu: SimpleNamespace, expected_present: bool
    ) -> None:
        from fpstune.settings import registry as registry_mod
        from fpstune.settings.discovery.network import register_adapter_settings

        monkeypatch.setattr("fpstune.utils.detect.get_cpu_detailed_info", lambda *_a, **_k: cpu)
        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        register_adapter_settings(reg, 5, "Ethernet", "802.3")
        present = reg.get("network:5:rss_base_processor") is not None
        assert present is expected_present
