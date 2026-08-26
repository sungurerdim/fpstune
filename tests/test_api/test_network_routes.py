"""Tests for the network adapter API routes (system_network.py).

`POST /api/network/adapter/{action}` disables and enables real NICs, so every
test replaces `_run_powershell_async` in the route module — nothing here may
ever touch this machine's adapters. What is asserted is the route's contract:
which requests are refused before a shell is built (bad action, no identifier,
no admin, wrong platform), how each script verdict maps to a response, and
that a hostile identifier can never break out of its single-quoted string.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.api.schemas import NetworkAdapterInfo

# A realistic PCI NIC instance id — the identifier the toggle endpoint takes.
INSTANCE_ID = "PCI\\VEN_8086&DEV_15F3&SUBSYS_00098086&REV_03\\3&11583659&0&C8"

ADAPTER_STATUS_JSON = (
    '{"Name": "Ethernet", "IsEnabled": true, "IsConnected": true, '
    '"AdapterType": "ethernet", "IPv4": "192.168.1.42", "Status": "Up"}'
)


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _adapter() -> NetworkAdapterInfo:
    return NetworkAdapterInfo(
        name="Ethernet",
        description="Intel(R) Ethernet Controller I225-V",
        adapter_type="Ethernet",
        status="Up",
        is_enabled=True,
        is_connected=True,
        mac_address="00-1B-21-3C-4D-5E",
        speed_mbps=2500,
        ipv4_address="192.168.1.42",
        interface_index=12,
        instance_id=INSTANCE_ID,
    )


def _ps(result: tuple[bool, str] | list[tuple[bool, str]]) -> AsyncMock:
    """A stand-in for `_run_powershell_async` so no PowerShell ever runs."""
    if isinstance(result, list):
        return AsyncMock(side_effect=result)
    return AsyncMock(return_value=result)


@contextmanager
def _windows(admin: bool = True) -> Iterator[None]:
    """Patch the route module onto Windows with (by default) admin rights, so
    these tests answer the same on any host the suite runs on."""
    with (
        patch("fpstune.api.routes.system_network.sys") as mock_sys,
        patch("fpstune.api.routes.system_network.is_admin", return_value=admin),
    ):
        mock_sys.platform = "win32"
        yield


# ---------------------------------------------------------------------------
# POST /api/network/refresh
# ---------------------------------------------------------------------------


class TestRefreshNetworkAdapters:
    """Tests for POST /api/network/refresh."""

    def test_refresh_returns_detected_adapters(self, client: TestClient) -> None:
        adapter = _adapter()
        with (
            patch("fpstune.api.routes.system_network.hardware_manager") as mock_hw,
            patch(
                "fpstune.api.routes.system_network.get_detailed_network_adapters",
                return_value=[adapter],
            ),
        ):
            response = client.post("/api/network/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["network_adapters"]) == 1
        assert data["network_adapters"][0]["name"] == "Ethernet"
        assert data["network_adapters"][0]["instance_id"] == INSTANCE_ID
        mock_hw.set_network_adapters.assert_called_once_with([adapter])

    def test_refresh_invalidates_only_the_network_cache(self, client: TestClient) -> None:
        """A granular refresh that also dropped monitors or GPU would put a
        multi-second re-detect behind a ~500 ms endpoint."""
        with (
            patch("fpstune.api.routes.system_network.hardware_manager") as mock_hw,
            patch(
                "fpstune.api.routes.system_network.get_detailed_network_adapters",
                return_value=[],
            ),
        ):
            response = client.post("/api/network/refresh")

        assert response.status_code == 200
        mock_hw.invalidate_cache.assert_called_once_with("network_adapters")

    def test_refresh_failure_reports_instead_of_crashing(self, client: TestClient) -> None:
        """The failure path: a broken detection answers success=False with an
        empty list, never a 500 the UI cannot render."""
        with (
            patch("fpstune.api.routes.system_network.hardware_manager"),
            patch(
                "fpstune.api.routes.system_network.get_detailed_network_adapters",
                side_effect=OSError("CIM query failed"),
            ),
        ):
            response = client.post("/api/network/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["network_adapters"] == []


# ---------------------------------------------------------------------------
# POST /api/network/adapter/{action}
# ---------------------------------------------------------------------------


class TestToggleNetworkAdapter:
    """Tests for POST /api/network/adapter/{action}."""

    def test_an_unknown_action_is_refused_before_anything_runs(self, client: TestClient) -> None:
        """The action lands in the PS script verbatim, so only the two known
        verbs may ever get that far."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_network._run_powershell_async", new=ps):
            response = client.post(
                "/api/network/adapter/destroy", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 400
        ps.assert_not_awaited()

    def test_no_identifier_at_all_is_refused(self, client: TestClient) -> None:
        """With neither identifier the script would have nothing to select an
        adapter by — and 'no filter' against Disable-NetAdapter is exactly the
        request that takes down every NIC on the machine."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_network._run_powershell_async", new=ps):
            response = client.post("/api/network/adapter/disable")

        assert response.status_code == 400
        ps.assert_not_awaited()

    def test_without_admin_rights_it_is_403(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with (
            _windows(admin=False),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post(
                "/api/network/adapter/disable", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 403
        ps.assert_not_awaited()

    def test_off_windows_it_is_400(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with (
            patch("fpstune.api.routes.system_network.sys") as mock_sys,
            patch("fpstune.api.routes.system_network.is_admin", return_value=True),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            mock_sys.platform = "linux"
            response = client.post(
                "/api/network/adapter/disable", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 400
        ps.assert_not_awaited()

    def test_enable_by_instance_id_reports_the_verified_state(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post(
                "/api/network/adapter/enable", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["enabled"] is True
        command = ps.call_args[0][0]
        assert INSTANCE_ID in command
        assert "$action = 'enable'" in command

    def test_disable_by_instance_id_reports_disabled(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post(
                "/api/network/adapter/disable", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_a_quote_in_the_instance_id_cannot_break_out_of_the_string(
        self, client: TestClient
    ) -> None:
        """The id is interpolated into a script that runs as admin, so the
        single-quote doubling is the entire injection defence here."""
        hostile = INSTANCE_ID + "'; Disable-NetAdapter *; '"
        ps = _ps((True, "OK"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post("/api/network/adapter/disable", params={"instance_id": hostile})

        assert response.status_code == 200
        command = ps.call_args[0][0]
        assert hostile not in command, "the raw quote reached PowerShell unescaped"
        assert hostile.replace("'", "''") in command

    def test_toggle_by_interface_index_builds_an_index_command(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post("/api/network/adapter/disable", params={"interface_index": 12})

        assert response.status_code == 200
        command = ps.call_args[0][0]
        assert "Disable-NetAdapter -InterfaceIndex 12" in command

    def test_a_non_integer_interface_index_is_a_validation_error(self, client: TestClient) -> None:
        """The index goes into the script unquoted, so anything that is not a
        bare integer must die at the type gate (SEC-14)."""
        ps = _ps((True, "OK"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post(
                "/api/network/adapter/disable",
                params={"interface_index": "12; Disable-NetAdapter *"},
            )

        assert response.status_code == 422
        ps.assert_not_awaited()

    def test_an_adapter_powershell_cannot_find_is_500_with_the_reason(
        self, client: TestClient
    ) -> None:
        ps = _ps((True, "ERROR: No matching NetAdapter found"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post(
                "/api/network/adapter/disable", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 500
        assert "No matching NetAdapter found" in response.json()["detail"]

    def test_a_state_change_that_never_verified_is_an_error_not_success(
        self, client: TestClient
    ) -> None:
        """The script polls WMI for the real hardware state; a timeout there
        means the adapter may not have changed, and reporting success anyway
        would be a false-done on a device mutation."""
        ps = _ps((True, "ERROR: State change timeout - adapter may not have changed"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post(
                "/api/network/adapter/enable", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 500
        assert "timeout" in response.json()["detail"].lower()

    def test_an_answer_the_route_does_not_know_is_500_not_success(self, client: TestClient) -> None:
        ps = _ps((True, "WARNING: something unexpected"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post(
                "/api/network/adapter/enable", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 500

    def test_a_powershell_launch_failure_is_500(self, client: TestClient) -> None:
        ps = _ps((False, "spawn failed"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post(
                "/api/network/adapter/disable", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 500

    def test_debug_lines_before_the_verdict_are_ignored(self, client: TestClient) -> None:
        """The script's own DEBUG chatter must not shadow the last-line verdict."""
        ps = _ps((True, "DEBUG: matched adapter Ethernet\nOK\n"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = client.post(
                "/api/network/adapter/enable", params={"instance_id": INSTANCE_ID}
            )

        assert response.status_code == 200
        assert response.json()["success"] is True


# ---------------------------------------------------------------------------
# POST /api/network/adapter/{adapter_name}/connection/{action}
# ---------------------------------------------------------------------------


def _post_connection(client: TestClient, adapter_name: str, action: str) -> Any:
    return client.post(f"/api/network/adapter/{quote(adapter_name, safe='')}/connection/{action}")


class TestToggleNetworkConnection:
    """Tests for POST /api/network/adapter/{name}/connection/{action}."""

    def test_an_unknown_action_is_refused_before_anything_runs(self, client: TestClient) -> None:
        ps = _ps((True, "ETHERNET"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = _post_connection(client, "Ethernet", "sever")

        assert response.status_code == 400
        ps.assert_not_awaited()

    def test_off_windows_it_is_400(self, client: TestClient) -> None:
        ps = _ps((True, "ETHERNET"))
        with (
            patch("fpstune.api.routes.system_network.sys") as mock_sys,
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            mock_sys.platform = "linux"
            response = _post_connection(client, "Ethernet", "disconnect")

        assert response.status_code == 400
        ps.assert_not_awaited()

    def test_an_adapter_that_does_not_exist_is_404(self, client: TestClient) -> None:
        ps = _ps((True, "NOT_FOUND"))
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = _post_connection(client, "Ghost Adapter", "disconnect")

        assert response.status_code == 404

    def test_wifi_disconnect_answers_with_the_wifi_shape(self, client: TestClient) -> None:
        """WiFi goes through netsh wlan, Ethernet through DHCP release — the
        response must say which path was taken or the UI shows the wrong verbs."""
        ps = _ps([(True, "WIFI"), (True, "OK")])
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = _post_connection(client, "Wi-Fi", "disconnect")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["adapter_type"] == "wifi"
        assert data["is_connected"] is False
        assert "wlan disconnect" in ps.call_args_list[1][0][0]

    def test_wifi_reconnect_reports_the_profile_it_joined(self, client: TestClient) -> None:
        ps = _ps([(True, "WIFI"), (True, "OK:HomeNet-5G")])
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = _post_connection(client, "Wi-Fi", "connect")

        assert response.status_code == 200
        data = response.json()
        assert data["is_connected"] is True
        assert data["profile"] == "HomeNet-5G"

    def test_ethernet_connect_renews_the_lease(self, client: TestClient) -> None:
        ps = _ps([(True, "ETHERNET"), (True, "OK")])
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = _post_connection(client, "Ethernet", "connect")

        assert response.status_code == 200
        data = response.json()
        assert data["adapter_type"] == "ethernet"
        assert data["is_connected"] is True
        assert "ipconfig /renew" in ps.call_args_list[1][0][0]

    def test_a_unicode_adapter_name_survives_the_round_trip(self, client: TestClient) -> None:
        """Windows localises adapter names, so a non-ASCII name is the normal
        case abroad, not an edge case."""
        name = "Drahtlos-Netzwerkverbindung 2"
        ps = _ps([(True, "WIFI"), (True, "OK")])
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = _post_connection(client, name, "disconnect")

        assert response.status_code == 200
        assert response.json()["adapter_name"] == name
        assert name in ps.call_args_list[0][0][0]

    def test_a_quote_in_the_adapter_name_cannot_break_out_of_the_string(
        self, client: TestClient
    ) -> None:
        hostile = "Ethernet'; Disable-NetAdapter *; '"
        ps = _ps([(True, "ETHERNET"), (True, "OK")])
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = _post_connection(client, hostile, "disconnect")

        assert response.status_code == 200
        detect_command = ps.call_args_list[0][0][0]
        assert hostile not in detect_command, "the raw quote reached PowerShell unescaped"
        assert hostile.replace("'", "''") in detect_command

    def test_a_connect_that_failed_is_500_with_the_reason(self, client: TestClient) -> None:
        ps = _ps([(True, "WIFI"), (True, "ERROR: No saved WiFi profiles found")])
        with (
            _windows(),
            patch("fpstune.api.routes.system_network._run_powershell_async", new=ps),
        ):
            response = _post_connection(client, "Wi-Fi", "connect")

        assert response.status_code == 500
        assert "No saved WiFi profiles" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/network/adapter/{adapter_name}/status
# ---------------------------------------------------------------------------
