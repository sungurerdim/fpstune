"""The self-check must catch the class of defect that shipped undetected.

The monitor correlation was dead for its whole life because the fallback
produced a *plausible* map — a wrong detection looks exactly like a right one
until an independent source disagrees. These tests feed the checks the shifted
enumeration from the original bug and assert a named disagreement comes out.
"""

from __future__ import annotations

from types import SimpleNamespace

from fpstune.utils.self_check import (
    SelfCheckReport,
    check_cpu_sources,
    check_gpu_sources,
    check_monitor_sources,
)

_GUID = "{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}"


def _monitor(name: str, hw_id: str, active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(name=name, hardware_id=hw_id, is_active=active)


RECORDS = [
    rf"\\.\DISPLAY1|1|\\?\DISPLAY#BBB0002#4&1b2c3d4e&0&UID5002#{_GUID}",
    rf"\\.\DISPLAY5|5|\\?\DISPLAY#CCC0003#4&1b2c3d4e&0&UID9003#{_GUID}",
    rf"\\.\DISPLAY2|0|\\?\DISPLAY#AAA0001#4&1b2c3d4e&0&UID1001#{_GUID}",
]
WMI = ["AAA0001", "BBB0002", "CCC0003"]


class TestTheShiftedMapCannotPassTheCheck:
    def test_the_a1_bug_produces_a_named_disagreement(self) -> None:
        """The old zip on this host: DISPLAY1→internal, DISPLAY5→neighbour,
        and the third panel dropped. Plausible — and caught, because WMI
        names a panel the report no longer accounts for."""
        shifted = [
            _monitor(r"\\.\DISPLAY1", "AAA0001"),
            _monitor(r"\\.\DISPLAY5", "BBB0002"),
        ]
        findings = check_monitor_sources(shifted, WMI, RECORDS)
        named = {f.name: f for f in findings}
        assert named["every_wmi_panel_accounted_for"].agrees is False
        assert "CCC0003" in named["every_wmi_panel_accounted_for"].detail

    def test_the_correct_report_passes_every_check(self) -> None:
        correct = [
            _monitor(r"\\.\DISPLAY1", "BBB0002"),
            _monitor(r"\\.\DISPLAY5", "CCC0003"),
            _monitor(r"\\.\DISPLAY2", "AAA0001", active=False),
        ]
        report = SelfCheckReport(findings=check_monitor_sources(correct, WMI, RECORDS))
        assert report.ok, [f.detail for f in report.disagreements]

    def test_a_phantom_identity_is_a_disagreement(self) -> None:
        """An identity WMI never enumerated cannot be a detection, only a bug."""
        phantom = [_monitor(r"\\.\DISPLAY1", "ZZZ9999")]
        findings = check_monitor_sources(phantom, WMI, RECORDS)
        named = {f.name: f for f in findings}
        assert named["no_reported_identity_wmi_never_saw"].agrees is False

    def test_an_attached_head_missing_from_the_report_is_a_disagreement(self) -> None:
        only_one = [_monitor(r"\\.\DISPLAY1", "BBB0002")]
        findings = check_monitor_sources(only_one, WMI, RECORDS)
        named = {f.name: f for f in findings}
        assert named["every_attached_screen_reported"].agrees is False
        assert "DISPLAY5" in named["every_attached_screen_reported"].detail

    def test_an_uncorrelated_active_screen_is_a_disagreement(self) -> None:
        blank = [_monitor(r"\\.\DISPLAY1", "")]
        findings = check_monitor_sources(blank, WMI, RECORDS)
        named = {f.name: f for f in findings}
        assert named["every_active_screen_has_an_identity"].agrees is False


class TestCpuCrossChecks:
    def test_wmi_disagreeing_with_the_scheduler_is_named(self) -> None:
        cpu = SimpleNamespace(
            logical_cores=8, physical_cores=8, p_cores=8, e_cores=0, is_hybrid=False
        )
        findings = check_cpu_sources(cpu, os_logical=16)
        named = {f.name: f for f in findings}
        assert named["logical_cores_agree_with_the_scheduler"].agrees is False

    def test_a_topology_that_does_not_sum_is_named(self) -> None:
        cpu = SimpleNamespace(
            logical_cores=20, physical_cores=14, p_cores=6, e_cores=4, is_hybrid=True
        )
        findings = check_cpu_sources(cpu, os_logical=20)
        named = {f.name: f for f in findings}
        assert named["pe_topology_sums_to_the_core_count"].agrees is False

    def test_an_unknown_topology_is_recorded_not_condemned(self) -> None:
        cpu = SimpleNamespace(
            logical_cores=16, physical_cores=8, p_cores=0, e_cores=0, is_hybrid=None
        )
        findings = check_cpu_sources(cpu, os_logical=16)
        named = {f.name: f for f in findings}
        assert named["pe_topology"].agrees is True
        assert "unknown" in named["pe_topology"].detail


class TestGpuCrossChecks:
    def test_two_sources_a_tier_apart_disagree(self) -> None:
        gpu = SimpleNamespace(vram_mb=4095)  # the clamp
        findings = check_gpu_sources(gpu, registry_vram_mb=16384)
        assert findings[0].agrees is False

    def test_a_rounding_step_is_not_a_disagreement(self) -> None:
        gpu = SimpleNamespace(vram_mb=8192)
        findings = check_gpu_sources(gpu, registry_vram_mb=8192)
        assert findings[0].agrees is True

    def test_a_single_source_is_recorded_not_assumed(self) -> None:
        gpu = SimpleNamespace(vram_mb=8192)
        findings = check_gpu_sources(gpu, registry_vram_mb=None)
        assert findings[0].agrees is True
        assert "no cross-check possible" in findings[0].detail


class TestFirstApplyGate:
    def test_the_check_runs_once_per_machine_and_never_again(self, tmp_path, monkeypatch) -> None:
        """The first write must not derive from a detection nobody
        cross-checked; every later write must not pay for it again."""
        import fpstune.utils.self_check as self_check

        monkeypatch.setattr(self_check, "get_config_dir", lambda: tmp_path)
        calls: list[int] = []

        def fake_run() -> self_check.SelfCheckReport:
            calls.append(1)
            (tmp_path / "selfcheck.json").write_text('{"ok": true, "findings": []}')
            return self_check.SelfCheckReport()

        monkeypatch.setattr(self_check, "run_self_check", fake_run)
        self_check.ensure_checked_before_first_apply()
        self_check.ensure_checked_before_first_apply()
        assert calls == [1]
