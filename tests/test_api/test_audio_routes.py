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

# A realistic MMDevice endpoint GUID, the shape the loudness-eq route validates.
DEVICE_GUID = "b7a3f2c1-4d5e-4f60-9a1b-2c3d4e5f6a7b"

# A realistic audio endpoint PnP instance id, the shape the enable route takes.
PNP_INSTANCE_ID = "SWD\\MMDEVAPI\\{0.0.0.00000000}.{" + DEVICE_GUID + "}"


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _device(device_id: str = DEVICE_GUID) -> AudioDeviceInfo:
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
        assert data["audio_devices"][0]["id"] == DEVICE_GUID
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


class TestToggleLoudnessEq:
    """Tests for POST /api/audio/device/{device_id}/loudness-eq."""

    def test_enable_writes_the_enable_bytes_for_the_given_device(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, DEVICE_GUID, enabled=True)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["device_id"] == DEVICE_GUID
        assert data["enabled"] is True
        command = ps.call_args[0][0]
        assert DEVICE_GUID in command
        # Bytes 8-9 = ff,ff is what "enabled" means in the FxProperties blob.
        assert "0xff,0xff" in command

    def test_disable_writes_the_disable_bytes(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, DEVICE_GUID, enabled=False)

        assert response.status_code == 200
        assert response.json()["enabled"] is False
        command = ps.call_args[0][0]
        assert "0xff,0xff" not in command

    def test_a_braced_guid_is_accepted(self, client: TestClient) -> None:
        """Registry tooling hands GUIDs back both bare and braced; refusing one
        spelling would break half the callers for no safety gain."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, "{" + DEVICE_GUID + "}")

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "hostile_id",
        [
            "not-a-guid",
            "",
            "b7a3f2c1-4d5e-4f60-9a1b",  # truncated GUID
            "$(Stop-Service -Name Audiosrv)",  # PowerShell subexpression
            "b7a3f2c1-4d5e-4f60-9a1b-2c3d4e5f6a7b'; regedit /s evil.reg; '",  # quote breakout
            "ÿb7a3f2c1-4d5e-4f60-9a1b-2c3d4e5f6a7b",  # non-ASCII prefix
        ],
    )
    def test_a_non_guid_device_id_never_reaches_powershell(
        self, client: TestClient, hostile_id: str
    ) -> None:
        """The endpoint interpolates the id into a script that takes registry
        ACL ownership as SYSTEM-adjacent work, so the GUID gate is the whole
        injection defence and must fire before any shell is built."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, hostile_id)

        # An empty path segment cannot match the route (404); everything else
        # must be rejected by the GUID validation (400).
        assert response.status_code in (400, 404)
        ps.assert_not_awaited()

    def test_missing_enabled_flag_is_a_validation_error(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = client.post(f"/api/audio/device/{DEVICE_GUID}/loudness-eq")

        assert response.status_code == 422
        ps.assert_not_awaited()

    def test_a_device_the_registry_does_not_hold_is_404(self, client: TestClient) -> None:
        ps = _ps((True, f"NOT_FOUND:{DEVICE_GUID}"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, DEVICE_GUID)

        assert response.status_code == 404

    def test_a_device_without_enhancement_support_is_400(self, client: TestClient) -> None:
        ps = _ps((True, "NOT_SUPPORTED"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, DEVICE_GUID)

        assert response.status_code == 400
        assert "does not support" in response.json()["detail"]

    def test_a_trustedinstaller_key_is_403_with_manual_steps(self, client: TestClient) -> None:
        """A protected key is not an error to retry — the user is told where in
        Windows to do it by hand instead."""
        ps = _ps((True, "TRUSTEDINSTALLER:Manual configuration required for this device"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, DEVICE_GUID)

        assert response.status_code == 403
        assert "Sound settings" in response.json()["detail"]

    def test_a_powershell_launch_failure_is_500(self, client: TestClient) -> None:
        ps = _ps((False, "The term 'powershell' is not recognized"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, DEVICE_GUID)

        assert response.status_code == 500

    def test_a_write_that_failed_every_method_is_500(self, client: TestClient) -> None:
        ps = _ps((True, "ERROR: Registry write failed after all methods"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, DEVICE_GUID)

        assert response.status_code == 500

    def test_an_answer_the_route_does_not_know_is_500_not_success(self, client: TestClient) -> None:
        """An unrecognised script answer must never be reported as applied —
        that is a silent false-success on a device mutation."""
        ps = _ps((True, "WARNING: something unexpected"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, DEVICE_GUID)

        assert response.status_code == 500

    def test_debug_lines_before_the_verdict_are_ignored(self, client: TestClient) -> None:
        """The script's own DEBUG chatter must not shadow the last-line verdict."""
        ps = _ps((True, "DEBUG: probing Render\nDEBUG: found key\nOK\n"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_loudness(client, DEVICE_GUID)

        assert response.status_code == 200
        assert response.json()["success"] is True


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

    def test_disable_runs_the_pnp_disable_for_that_instance(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, PNP_INSTANCE_ID, enabled=False)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["enabled"] is False
        assert data["device_id"] == PNP_INSTANCE_ID
        command = ps.call_args[0][0]
        assert "Disable-PnpDevice" in command
        assert PNP_INSTANCE_ID in command

    def test_enable_runs_the_pnp_enable(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, PNP_INSTANCE_ID, enabled=True)

        assert response.status_code == 200
        assert "Enable-PnpDevice" in ps.call_args[0][0]

    def test_a_quote_in_the_device_id_cannot_break_out_of_the_string(
        self, client: TestClient
    ) -> None:
        """This endpoint takes any PnP instance id, so unlike loudness-eq there
        is no GUID gate — the single-quote doubling is the entire defence and a
        bare quote in the built command would hand the id shell control."""
        hostile = PNP_INSTANCE_ID + "'; Stop-Service -Name Audiosrv; '"
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, hostile, enabled=False)

        assert response.status_code == 200
        command = ps.call_args[0][0]
        assert hostile not in command, "the raw quote reached PowerShell unescaped"
        assert hostile.replace("'", "''") in command

    def test_an_oversized_device_id_is_refused_before_powershell(self, client: TestClient) -> None:
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, "A" * 501, enabled=False)

        assert response.status_code == 400
        ps.assert_not_awaited()

    def test_a_maximum_length_device_id_is_still_served(self, client: TestClient) -> None:
        """The boundary itself: 500 characters is the last legal length, and an
        off-by-one here would refuse real (long) composite instance ids."""
        ps = _ps((True, "OK"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, "A" * 500, enabled=True)

        assert response.status_code == 200

    def test_a_device_powershell_cannot_find_is_500_with_the_reason(
        self, client: TestClient
    ) -> None:
        ps = _ps((True, "ERROR: No matching Win32 devices found"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, PNP_INSTANCE_ID, enabled=False)

        assert response.status_code == 500
        assert "No matching Win32 devices" in response.json()["detail"]

    def test_a_powershell_launch_failure_is_500(self, client: TestClient) -> None:
        ps = _ps((False, "spawn failed"))
        with patch("fpstune.api.routes.system_audio._run_powershell_async", new=ps):
            response = _post_enabled(client, PNP_INSTANCE_ID, enabled=True)

        assert response.status_code == 500
