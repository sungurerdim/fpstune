"""Tests for the audio device API routes (system_audio.py).

All three endpoints mutate real devices through PowerShell, so every test
replaces `_run_powershell_async` in the route module — nothing here may ever
reach this machine's audio stack. What is asserted instead is the route's own
contract: which inputs are refused before a shell is even built, what each
sentinel the script prints back maps to, and that a hostile device id can
never break out of its single-quoted PowerShell string.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.api.schemas import AudioDeviceInfo

# A realistic MMDevice endpoint GUID and the endpoint ids detection builds from it.
DEVICE_GUID = "b7a3f2c1-4d5e-4f60-9a1b-2c3d4e5f6a7b"
OUTPUT_ID = "{0.0.0.00000000}.{" + DEVICE_GUID + "}"
INPUT_ID = "{0.0.1.00000000}.{" + DEVICE_GUID + "}"


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _device(device_id: str = OUTPUT_ID) -> AudioDeviceInfo:
    return AudioDeviceInfo(
        id=device_id,
        name="Speakers (Realtek(R) Audio)",
        device_type="Playback",
        is_default=True,
        is_enabled=True,
        driver="Realtek Audio Driver",
        loudness_eq_supported=True,
        loudness_eq_enabled=False,
    )


def _ps(result: tuple[bool, str] | list[tuple[bool, str]]) -> AsyncMock:
    """A stand-in for `_run_powershell_async` so no PowerShell ever runs."""
    if isinstance(result, list):
        return AsyncMock(side_effect=result)
    return AsyncMock(return_value=result)


# ---------------------------------------------------------------------------
# POST /api/audio/refresh
# ---------------------------------------------------------------------------


class TestRefreshAudioDevices:
    """Tests for POST /api/audio/refresh."""

    def test_refresh_returns_detected_devices(self, client: TestClient) -> None:
        device = _device()
        with (
            patch("fpstune.api.routes.system_audio.hardware_manager") as mock_hw,
            patch(
                "fpstune.api.routes.system_audio.get_audio_devices",
                return_value=[device],
            ),
        ):
            response = client.post("/api/audio/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["audio_devices"]) == 1
        assert data["audio_devices"][0]["id"] == OUTPUT_ID
        assert data["audio_devices"][0]["name"] == "Speakers (Realtek(R) Audio)"
        mock_hw.set_audio_devices.assert_called_once_with([device])

    def test_refresh_invalidates_only_the_audio_cache(self, client: TestClient) -> None:
        """A granular refresh that also dropped monitors or GPU would put a
        multi-second re-detect behind a ~300 ms endpoint."""
        with (
            patch("fpstune.api.routes.system_audio.hardware_manager") as mock_hw,
            patch("fpstune.api.routes.system_audio.get_audio_devices", return_value=[]),
        ):
            response = client.post("/api/audio/refresh")

        assert response.status_code == 200
        mock_hw.invalidate_cache.assert_called_once_with("audio_devices")

    def test_refresh_failure_reports_instead_of_crashing(self, client: TestClient) -> None:
        """The failure path: a broken detection answers success=False with an
        empty list, never a 500 the UI cannot render."""
        with (
            patch("fpstune.api.routes.system_audio.hardware_manager"),
            patch(
                "fpstune.api.routes.system_audio.get_audio_devices",
                side_effect=OSError("WMI query failed"),
            ),
        ):
            response = client.post("/api/audio/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["audio_devices"] == []


# ---------------------------------------------------------------------------
# POST /api/audio/device/{device_id}/loudness-eq
# ---------------------------------------------------------------------------


def _post_loudness(client: TestClient, device_id: str, *, enabled: bool = True) -> Any:
    return client.post(
        f"/api/audio/device/{quote(device_id, safe='')}/loudness-eq",
        params={"enabled": enabled},
    )


_HOSTILE_IDS = [
    "not-a-guid",
    DEVICE_GUID,  # a bare GUID is no longer an endpoint id: the flow is missing
    "{0.0.2.00000000}.{" + DEVICE_GUID + "}",  # no such flow
    OUTPUT_ID + "\n",  # trailing newline must not slip past an anchored match
    OUTPUT_ID + "'; Stop-Service -Name Audiosrv; '",  # quote breakout
    "$(Stop-Service -Name Audiosrv)",  # PowerShell subexpression
    "PCI\\VEN_10DE&DEV_2484\\4&2A6B4F3&0&0008",  # a GPU, not an audio endpoint
    "ÿ" + OUTPUT_ID,  # non-ASCII prefix
]


class TestToggleLoudnessEq:
    """Tests for POST /api/audio/device/{device_id}/loudness-eq."""

    def test_enable_writes_the_enable_flag_to_that_output(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, OUTPUT_ID, enabled=True)

        assert response.status_code == 200
        data = response.json()
        assert data == {
            "success": True,
            "device_id": OUTPUT_ID,
            "enabled": True,
            "message": "Volume normalization enabled",
        }
        command = ps.call_args[0][0]
        assert "\\Render\\{" + DEVICE_GUID + "}" in command
        # Bytes 8-9 = ff,ff is what "on" means in the VT_BOOL blob.
        assert "0x00,0x00,0x00,0xff,0xff,0x00,0x00)" in command
        assert "$enable = $true" in command

    def test_disable_writes_the_off_flag(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, OUTPUT_ID, enabled=False)

        assert response.status_code == 200
        assert response.json()["enabled"] is False
        command = ps.call_args[0][0]
        assert "0xff,0xff" not in command
        assert "$enable = $false" in command

    def test_the_write_is_the_minimal_rights_open_and_nothing_heavier(
        self, client: TestClient
    ) -> None:
        """The regression this rewrite exists for. The old route took ownership of
        the key and granted Administrators FullControl (never reverted), imported a
        .reg file through regedit, and restarted AudioEndpointBuilder — which cut
        every sound on the machine — on each toggle."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            _post_loudness(client, OUTPUT_ID)

        command = ps.call_args[0][0]
        assert "Set-FpsEndpointValue" in command
        assert "'SetValue,QueryValues'" in command
        for forbidden in (
            "TakeOwnership",
            "SetAccessControl",
            "regedit",
            "Restart-Service",
            "AudioEndpointBuilder",
        ):
            assert forbidden not in command

    def test_support_is_microsofts_effects_in_the_chain_not_any_fx_key(
        self, client: TestClient
    ) -> None:
        """An FxProperties key exists on most outputs; Loudness Equalization exists
        only where Microsoft's pre-mix or post-mix object is loaded."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            _post_loudness(client, OUTPUT_ID)

        command = ps.call_args[0][0]
        assert "Test-FpsMsSysFx $fx" in command
        assert "62dc1a93-ae24-464c-a43e-452f824c4250" in command
        assert "637c490d-eee3-4c0a-973f-371958802da2" in command

    def test_turning_it_on_also_clears_disable_sysfx_and_reads_both_back(
        self, client: TestClient
    ) -> None:
        """'On' under a disabled chain is a state Windows shows and never plays —
        the "it is ticked but nothing happens" report."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            _post_loudness(client, OUTPUT_ID)

        command = ps.call_args[0][0]
        assert "$sysfxKey 0 'DWord'" in command
        assert "$on = (Test-FpsLeqOn $after) -and ($after.$sysfxKey -ne 1)" in command

    def test_an_input_is_refused_before_powershell(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, INPUT_ID)

        assert response.status_code == 400
        ps.assert_not_awaited()

    @pytest.mark.parametrize("hostile_id", _HOSTILE_IDS)
    def test_anything_but_an_endpoint_id_never_reaches_powershell(
        self, client: TestClient, hostile_id: str
    ) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, hostile_id)

        assert response.status_code in (400, 404)
        ps.assert_not_awaited()

    def test_missing_enabled_flag_is_a_validation_error(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = client.post(f"/api/audio/device/{quote(OUTPUT_ID, safe='')}/loudness-eq")

        assert response.status_code == 422
        ps.assert_not_awaited()

    def test_an_output_the_registry_does_not_hold_is_404(self, client: TestClient) -> None:
        with patch(
            "fpstune.api.routes.system_audio._run_powershell_async", new=_ps((True, "NOT_FOUND"))
        ):
            response = _post_loudness(client, OUTPUT_ID)

        assert response.status_code == 404

    def test_an_output_without_microsofts_effects_is_400_with_the_reason(
        self, client: TestClient
    ) -> None:
        with patch(
            "fpstune.api.routes.system_audio._run_powershell_async",
            new=_ps((True, "NOT_SUPPORTED")),
        ):
            response = _post_loudness(client, OUTPUT_ID)

        assert response.status_code == 400
        assert "Microsoft's system effects" in response.json()["detail"]

    def test_a_powershell_launch_failure_is_500(self, client: TestClient) -> None:
        ps = _ps((False, "The term 'powershell' is not recognized"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, OUTPUT_ID)

        assert response.status_code == 500

    def test_a_write_that_did_not_hold_is_500_with_the_scripts_reason(
        self, client: TestClient
    ) -> None:
        ps = _ps((True, "ERROR: the output did not keep the new state"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, OUTPUT_ID)

        assert response.status_code == 500
        assert response.json()["detail"] == "the output did not keep the new state"

    def test_an_answer_the_route_does_not_know_is_500_not_success(self, client: TestClient) -> None:
        """An unrecognised script answer must never be reported as applied —
        that is a silent false-success on a device mutation."""
        ps = _ps((True, "WARNING: something unexpected"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, OUTPUT_ID)

        assert response.status_code == 500

    def test_chatter_before_the_verdict_is_ignored(self, client: TestClient) -> None:
        ps = _ps((True, "probing Render\nOK\n"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, OUTPUT_ID)

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/audio/device/{device_id}/enabled
# ---------------------------------------------------------------------------


def _post_enabled(client: TestClient, device_id: str, *, enabled: bool) -> Any:
    return client.post(
        f"/api/audio/device/{quote(device_id, safe='')}/enabled",
        params={"enabled": enabled},
    )


class TestToggleAudioDevice:
    """Tests for POST /api/audio/device/{device_id}/enabled."""

    def test_disable_targets_the_endpoints_own_pnp_instance(self, client: TestClient) -> None:
        """The id the card holds is the endpoint id; the PnP instance is derived
        from it. The old card sent a bare GUID, which Get-PnpDevice never found, so
        every toggle answered 500."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, OUTPUT_ID, enabled=False)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["enabled"] is False
        assert data["device_id"] == OUTPUT_ID
        command = ps.call_args[0][0]
        assert "Disable-PnpDevice -InstanceId 'SWD\\MMDEVAPI\\" + OUTPUT_ID + "'" in command

    def test_enable_runs_the_pnp_enable_for_an_input_too(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, INPUT_ID, enabled=True)

        assert response.status_code == 200
        assert (
            "Enable-PnpDevice -InstanceId 'SWD\\MMDEVAPI\\" + INPUT_ID + "'" in (ps.call_args[0][0])
        )

    @pytest.mark.parametrize("hostile_id", _HOSTILE_IDS)
    def test_only_an_audio_endpoint_can_be_switched(
        self, client: TestClient, hostile_id: str
    ) -> None:
        """The route used to take any PnP instance id up to 500 characters, so it
        could disable a GPU or a disk controller. Now it switches audio endpoints
        and nothing else, refused before a shell is built."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, hostile_id, enabled=False)

        assert response.status_code in (400, 404)
        ps.assert_not_awaited()

    def test_a_device_powershell_cannot_find_is_500_with_the_reason(
        self, client: TestClient
    ) -> None:
        ps = _ps((True, "ERROR: No matching Win32 devices found"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, OUTPUT_ID, enabled=False)

        assert response.status_code == 500
        assert response.json()["detail"] == "No matching Win32 devices found"

    def test_a_powershell_launch_failure_is_500(self, client: TestClient) -> None:
        ps = _ps((False, "spawn failed"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, OUTPUT_ID, enabled=True)

        assert response.status_code == 500

    def test_silence_is_not_success(self, client: TestClient) -> None:
        ps = _ps((True, ""))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, OUTPUT_ID, enabled=True)

        assert response.status_code == 500
