"""The batched detect paths must answer identically to the commands they replace.

A green suite is not evidence for a cache: the batch can return a different value
from the per-setting command and every other test still passes. These pin the
wiring and the sentinels; equivalence against live Windows was measured
separately (0 mismatches over tcp_timestamps, tcp_ecn and both power_management
settings) before the fast paths were switched on.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from fpstune.settings.executors import netsh as netsh_mod
from fpstune.settings.executors import ps_batch as ps_batch_mod
from fpstune.settings.registry import SettingsRegistry


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    return SettingsRegistry()


@pytest.fixture(scope="module")
def adapter_backed_registry(registry: SettingsRegistry) -> SettingsRegistry:
    """A registry that actually enumerated NICs, or a failure saying it did not.

    The per-adapter settings only exist if ``_query_active_adapters`` answered
    inside its timeout. Under load it sometimes returns nothing, and every
    assertion about those settings then reads an empty registry as "never
    registered" — the test failed twice in five runs with a message naming the
    wrong cause, and a weaker assertion would have passed vacuously instead.

    ``HardwareProbes.active_adapters`` is memoised by the same ``probe_once``
    the discovery pass used, so asking here re-reads that answer rather than
    re-running the query.
    """
    if sys.platform != "win32":
        pytest.skip("NIC enumeration is a Windows query; there is nothing to read here")

    if not registry._probes.active_adapters():
        pytest.fail(
            "NIC enumeration returned no adapters, so no per-adapter setting was "
            "registered and the assertions below would have had nothing to check. "
            "This is a measurement failure, not a registration gap: re-run on an "
            "unloaded machine. A real gap looks different — adapters enumerated, "
            "settings still absent."
        )
    return registry


class TestTcpSnapshotFastPath:
    def test_the_extra_properties_are_in_the_one_query(self) -> None:
        # If these fall out of the snapshot the settings silently go back to
        # spawning their own Get-NetTCPSetting, which is exactly what they did.
        assert "EcnCapability" in netsh_mod.EXTRA_TCP_PROPERTIES
        assert "Timestamps" in netsh_mod.EXTRA_TCP_PROPERTIES

    def test_reads_a_property_out_of_the_snapshot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(netsh_mod, "_tcp_snapshot", lambda: {"Timestamps": "disabled"})
        assert netsh_mod.get_tcp_property("Timestamps") == "disabled"

    def test_property_lookup_is_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Snapshot keys keep the property's casing while values are lowercased,
        # so a caller spelling it differently must not silently miss.
        monkeypatch.setattr(netsh_mod, "_tcp_snapshot", lambda: {"EcnCapability": "enabled"})
        assert netsh_mod.get_tcp_property("ecncapability") == "enabled"

    def test_absent_property_reports_not_available_not_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "disabled" would be a claim about the machine; the per-setting scripts
        # answered 'not_available' for an unreadable object and the value_maps
        # still expect that.
        monkeypatch.setattr(netsh_mod, "_tcp_snapshot", lambda: {})
        assert netsh_mod.get_tcp_property("Timestamps") == netsh_mod.TCP_PROPERTY_MISSING

    @pytest.mark.parametrize(
        ("setting_id", "prop"),
        [("network:tcp_timestamps", "Timestamps"), ("network:tcp_ecn", "EcnCapability")],
    )
    def test_settings_are_wired_to_the_snapshot(
        self, registry: SettingsRegistry, setting_id: str, prop: str
    ) -> None:
        s = registry.get(setting_id)
        assert s is not None
        assert s.detect_args.get("batch_tcp") == prop
        # The single-setting command stays as the fallback outside a scan.
        assert "Get-NetTCPSetting" in s.detect_command


class TestAdapterPowerFastPath:
    def test_reads_a_state_by_interface_index(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ps_batch_mod, "prefetch_adapter_power", lambda: {"17": "Disabled"})
        assert ps_batch_mod.get_adapter_power_state(17) == "Disabled"
        assert ps_batch_mod.get_adapter_power_state("17") == "Disabled"

    def test_unknown_adapter_falls_back_to_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Matches what the per-setting command answered when it could not
        # resolve the PnP device: Enabled, i.e. "Windows may still power it down".
        monkeypatch.setattr(ps_batch_mod, "prefetch_adapter_power", lambda: {})
        assert ps_batch_mod.get_adapter_power_state(99) == "Enabled"
        assert ps_batch_mod.ADAPTER_POWER_MISSING == "Enabled"

    def test_every_power_management_setting_is_batched(
        self, adapter_backed_registry: SettingsRegistry
    ) -> None:
        found = [s for s in adapter_backed_registry.get_all() if s.id.endswith(":power_management")]
        assert found, (
            "adapters were enumerated but no per-adapter power_management setting "
            "was registered — a real registration gap"
        )
        for s in found:
            assert s.detect_args.get("batch_pnp_power") is True, s.id
            # ifindex must survive alongside the batch flag or the snapshot
            # cannot be indexed.
            assert "ifindex" in s.detect_args, s.id


class TestPrefetchRegistration:
    @pytest.mark.parametrize("arg", ["batch_tcp", "batch_pnp_power"])
    def test_a_batch_arg_has_a_prefetcher_behind_it(self, arg: str) -> None:
        # A batch hint with no prefetcher registered means the first setting to
        # ask pays the full query inside a worker thread, serialising the scan.
        import inspect

        from fpstune.settings import detection

        source = inspect.getsource(detection.DetectionEngine.detect_all)
        assert arg in source, f"{arg} has no prefetch branch in detect_all"

    def test_settings_declaring_a_batch_arg_exist_for_each_prefetcher(
        self, adapter_backed_registry: SettingsRegistry
    ) -> None:
        # batch_pnp_power is only ever declared by a per-adapter setting, so this
        # needs the registry that proved it enumerated some.
        all_args: set[str] = set()
        for s in adapter_backed_registry.get_all():
            all_args |= set(s.detect_args)
        for arg in ("batch_tcp", "batch_pnp_power"):
            assert arg in all_args, f"{arg} prefetcher exists but nothing uses it"


class TestSnapshotShape:
    def test_power_snapshot_keys_are_strings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # InterfaceIndex arrives as an int from the settings and as a JSON key
        # (string) from PowerShell; storing anything else makes every lookup miss.
        captured: dict[str, Any] = {}

        def fake_run(*_a: object, **_k: object) -> tuple[bool, str]:
            return True, '{"17":"Disabled","4":"Enabled"}'

        monkeypatch.setattr(ps_batch_mod, "run_powershell", fake_run)
        monkeypatch.setattr(ps_batch_mod.sys, "platform", "win32")
        captured = ps_batch_mod._fetch_adapter_power_snapshot()
        assert captured == {"17": "Disabled", "4": "Enabled"}
        assert all(isinstance(k, str) for k in captured)

    def test_unparseable_output_yields_an_empty_snapshot_not_a_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ps_batch_mod, "run_powershell", lambda *_a, **_k: (True, "not json"))
        monkeypatch.setattr(ps_batch_mod.sys, "platform", "win32")
        assert ps_batch_mod._fetch_adapter_power_snapshot() == {}
