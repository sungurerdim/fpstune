"""A batch detect that could not read answers "could not read", never a value.

Issue #104 class B. Measured: ``network:<nic>:power_management`` on Wi-Fi wrote
PnPCapabilities=24 (Disabled), then verify read "Enabled" — the batch script
seeded ``$state = 'Enabled'`` and swallowed every error, so a read during the
adapter restart reported the seed. The same shape sat in the service and
adapter-property snapshots, where a failed read became an empty map and so
"service not installed" / "property not supported" (both ABSENT_READINGS).

The notion reused here is the detection error: ``(None, "<reason>")``, which
``DetectionEngine`` turns into ``DetectionResult.error`` with a null value.
"""

from __future__ import annotations

import json
import sys
from contextlib import AbstractContextManager
from unittest.mock import patch

import pytest

from fpstune.settings.applicability import is_absent_reading
from fpstune.settings.definitions import network
from fpstune.settings.executors import adapter_restart
from fpstune.settings.executors import ps_batch as ps_batch_mod
from fpstune.settings.executors.powershell import PowerShellExecutor
from fpstune.settings.executors.ps_batch import (
    ADAPTER_PROPERTY_MISSING,
    _fetch_adapter_power_snapshot,
    _fetch_adapter_properties_snapshot,
    _fetch_services_snapshot,
    get_adapter_power_state,
    get_adapter_property,
    get_service_start_type,
    init_scan_cache,
    reset_scan_cache,
)
from fpstune.settings.registry import SettingsRegistry

pytestmark = pytest.mark.usefixtures("_on_windows")


@pytest.fixture
def _on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    # Both the batch fetchers and the executor stand down off Windows; the
    # PowerShell they would run is scripted here, so the paths run on any host.
    monkeypatch.setattr(sys, "platform", "win32")


def _run(output: str, ok: bool = True) -> AbstractContextManager[object]:
    return patch.object(ps_batch_mod, "run_powershell", lambda *_a, **_k: (ok, output))


def _no_restart_running() -> AbstractContextManager[object]:
    return patch.object(adapter_restart, "wait_for_restarts", lambda *_a, **_k: True)


# ---------------------------------------------------------------------------
# services
# ---------------------------------------------------------------------------


class TestServices:
    def test_a_failed_read_is_not_service_not_installed(self) -> None:
        with _run("access denied", ok=False):
            assert get_service_start_type("SysMain") is None

    def test_a_readable_list_without_the_service_still_says_not_found(self) -> None:
        listing = json.dumps([{"Name": "Spooler", "StartType": 2}])
        with _run(listing):
            assert get_service_start_type("SysMain") == "not_found"

    def test_a_failed_read_is_not_cached_as_an_answer_that_hides_the_failure(self) -> None:
        cache, token = init_scan_cache()
        try:
            with _run("", ok=False):
                assert get_service_start_type("SysMain") is None
        finally:
            reset_scan_cache(token)
        assert cache["services_snapshot"] is None

    def test_the_executor_reports_a_detection_error_not_an_absent_reading(self) -> None:
        setting = SettingsRegistry().get("services:SysMain")
        assert setting is not None
        with _run("", ok=False):
            value, error = PowerShellExecutor().detect(setting)
        assert value is None
        assert error
        assert not is_absent_reading(value)


# ---------------------------------------------------------------------------
# adapter advanced properties
# ---------------------------------------------------------------------------


class TestAdapterProperties:
    @pytest.mark.parametrize(
        "output",
        ["", "error:No MSFT_NetAdapter objects found", "{ not json"],
        ids=["empty-output", "script-reported-error", "malformed-json"],
    )
    def test_a_failed_query_is_an_unread_snapshot(self, output: str) -> None:
        with _run(output):
            assert _fetch_adapter_properties_snapshot() is None

    def test_a_powershell_failure_is_an_unread_snapshot(self) -> None:
        with _run("boom", ok=False):
            assert _fetch_adapter_properties_snapshot() is None

    def test_no_rows_is_a_real_answer_and_reads_as_not_supported(self) -> None:
        with _run("[]"):
            assert _fetch_adapter_properties_snapshot() == {}
            assert get_adapter_property(7, "*FlowControl") == ADAPTER_PROPERTY_MISSING

    def test_a_failed_query_is_not_reported_as_not_supported(self) -> None:
        with _run("", ok=False):
            assert get_adapter_property(7, "*FlowControl") is None

    def test_rows_are_indexed_by_interface_and_keyword(self) -> None:
        rows = json.dumps(
            [{"InterfaceIndex": 7, "RegistryKeyword": "*FlowControl", "RegistryValue": ["3"]}]
        )
        with _run(rows):
            assert get_adapter_property(7, "*FlowControl") == "3"

    def test_the_executor_reports_a_detection_error_not_an_absent_reading(self) -> None:
        setting = network.create_eee_setting(7, "Ethernet")
        assert setting.detect_args.get("batch_adapter_keyword")
        with _run("", ok=False):
            value, error = PowerShellExecutor().detect(setting)
        assert value is None
        assert error
        assert not is_absent_reading(value)


# ---------------------------------------------------------------------------
# adapter PnP power state (the measured case)
# ---------------------------------------------------------------------------


class TestAdapterPower:
    def test_an_adapter_missing_from_the_answer_is_unknown_not_enabled(self) -> None:
        # The script omits an adapter it could not resolve or read.
        with _run('{"17":"Disabled"}'), _no_restart_running():
            assert get_adapter_power_state(17) == "Disabled"
            assert get_adapter_power_state(4) is None

    def test_a_readable_adapter_with_the_stock_state_is_enabled(self) -> None:
        with _run('{"4":"Enabled"}'), _no_restart_running():
            assert get_adapter_power_state(4) == "Enabled"

    @pytest.mark.parametrize("output", ["", "error:x", "not json", "[1]"])
    def test_a_failed_read_makes_the_whole_snapshot_unread(self, output: str) -> None:
        with _run(output), _no_restart_running():
            assert _fetch_adapter_power_snapshot() is None
            assert get_adapter_power_state(4) is None

    def test_the_executor_reports_a_detection_error_not_the_default(self) -> None:
        setting = network.create_power_management_setting(4, "Wi-Fi")
        assert setting.detect_args.get("batch_pnp_power") is True
        with _run('{"17":"Disabled"}'), _no_restart_running():
            value, error = PowerShellExecutor().detect(setting)
        assert value is None
        assert error
        assert "Enabled" not in str(value)

    def test_the_executor_returns_the_state_when_it_was_read(self) -> None:
        setting = network.create_power_management_setting(4, "Wi-Fi")
        with _run('{"4":"Disabled"}'), _no_restart_running():
            assert PowerShellExecutor().detect(setting) == ("Disabled", None)

    def test_the_read_waits_for_a_restart_in_flight_before_it_queries(self) -> None:
        order: list[str] = []

        def waiter(*_a: object, **_k: object) -> bool:
            order.append("wait")
            return True

        def run(*_a: object, **_k: object) -> tuple[bool, str]:
            order.append("query")
            return True, '{"4":"Disabled"}'

        with (
            patch.object(adapter_restart, "wait_for_restarts", waiter),
            patch.object(ps_batch_mod, "run_powershell", run),
        ):
            assert _fetch_adapter_power_snapshot() == {"4": "Disabled"}
        assert order == ["wait", "query"]


def test_the_services_fetch_off_windows_stays_an_empty_map(monkeypatch: pytest.MonkeyPatch) -> None:
    # Off Windows nothing is read at all; the executor refuses before asking.
    monkeypatch.setattr(sys, "platform", "linux")
    assert _fetch_services_snapshot() == {}
