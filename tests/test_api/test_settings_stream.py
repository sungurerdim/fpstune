"""Tests for SSE streaming bulk apply/reset routes (settings_stream.py)."""

from __future__ import annotations

import contextlib
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE text/event-stream into a list of JSON objects."""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:") :].strip()
            with contextlib.suppress(json.JSONDecodeError):
                events.append(json.loads(payload))
    return events


def _make_apply_response(
    *,
    success: bool = True,
    new_value: str = "1",
    requires_reboot: bool = False,
    skipped: bool = False,
    error: str | None = None,
    verified: bool | None = True,
    freed_bytes: int | None = None,
    size_after_bytes: int | None = None,
) -> MagicMock:
    r = MagicMock()
    r.success = success
    r.new_value = new_value
    r.requires_reboot = requires_reboot
    r.skipped = skipped
    r.error = error
    # The stream now reports the verification outcome computed by
    # _finalize_apply_response instead of re-deriving it locally.
    r.verified = verified
    # Real values, because the `applied` event carries them into json.dumps: a
    # MagicMock here takes the whole stream down. None is what every non-cleanup
    # setting reports.
    r.freed_bytes = freed_bytes
    r.size_after_bytes = size_after_bytes
    return r


def _make_setting(
    setting_id: str,
    apply_type_value: str = "registry",
    recommended_value: str = "1",
    default_value: str = "0",
    requires_reboot: bool = False,
) -> MagicMock:
    s = MagicMock()
    s.id = setting_id
    s.apply_type = MagicMock()
    s.apply_type.value = apply_type_value
    s.recommended_value = recommended_value
    s.default_value = default_value
    s.requires_reboot = requires_reboot
    s.apply_args = {}
    # The `started` event names the setting and says how long it takes, so the
    # row can label itself before the command has printed anything. These have to
    # be real values: a MagicMock reaches json.dumps and takes the whole stream
    # down with it.
    s.display_name = setting_id.rsplit(":", 1)[-1].replace("_", " ").title()
    s.duration_estimate = ""
    s.progress_pattern = None
    return s


# ---------------------------------------------------------------------------
# POST /api/settings/bulk/stream-apply
# ---------------------------------------------------------------------------


class TestBulkStreamApply:
    """Tests for POST /api/settings/bulk/stream-apply."""

    def test_empty_ids_returns_done_event(self, client: TestClient) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
        ):
            response = client.post("/api/settings/bulk/stream-apply", json={"ids": []})

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = _parse_sse(response.text)
        done = next((e for e in events if e.get("event") == "done"), None)
        assert done is not None
        assert done["total"] == 0
        assert done["succeeded"] == 0
        assert done["failed"] == 0

    def test_unknown_setting_yields_failed_event(self, client: TestClient) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = None  # unknown ID

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
        ):
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["nonexistent:setting"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        failed = [e for e in events if e.get("event") == "failed"]
        assert len(failed) == 1
        assert failed[0]["id"] == "nonexistent:setting"
        assert "Unknown setting" in failed[0]["error"]

    def test_successful_apply_emits_applied_and_verified(self, client: TestClient) -> None:
        setting = _make_setting("core:game_mode", recommended_value="1", default_value="0")
        apply_resp = _make_apply_response(success=True, new_value="1")

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch(
                "fpstune.api.routes.settings_stream._apply_single_setting",
                return_value=(setting, apply_resp),
            ),
        ):
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["core:game_mode"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        event_types = [e.get("event") for e in events]
        assert "started" in event_types
        assert "applied" in event_types
        assert "verified" in event_types
        assert "done" in event_types

        done = next(e for e in events if e.get("event") == "done")
        assert done["succeeded"] == 1
        assert done["failed"] == 0

    def test_failed_apply_emits_failed_event(self, client: TestClient) -> None:
        setting = _make_setting("core:bad_setting")
        apply_resp = _make_apply_response(success=False, error="Access denied")

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch(
                "fpstune.api.routes.settings_stream._apply_single_setting",
                return_value=(setting, apply_resp),
            ),
        ):
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["core:bad_setting"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        failed = [e for e in events if e.get("event") == "failed"]
        assert len(failed) == 1
        assert "Access denied" in failed[0]["error"]

        done = next(e for e in events if e.get("event") == "done")
        assert done["failed"] == 1
        assert done["succeeded"] == 0

    def test_skipped_setting_emits_skipped_event(self, client: TestClient) -> None:
        setting = _make_setting("core:skipped_setting")
        apply_resp = _make_apply_response(skipped=True)

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch(
                "fpstune.api.routes.settings_stream._apply_single_setting",
                return_value=(setting, apply_resp),
            ),
        ):
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["core:skipped_setting"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        skipped = [e for e in events if e.get("event") == "skipped"]
        assert len(skipped) == 1

    def test_multiple_settings_all_succeed(self, client: TestClient) -> None:
        ids = ["core:setting_a", "core:setting_b", "timer:hpet"]
        settings = {sid: _make_setting(sid) for sid in ids}
        apply_resp = _make_apply_response(success=True, new_value="1")

        mock_registry = MagicMock()
        mock_registry.get.side_effect = lambda sid: settings.get(sid)

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch(
                "fpstune.api.routes.settings_stream._apply_single_setting",
                return_value=(MagicMock(), apply_resp),
            ),
        ):
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ids},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        done = next(e for e in events if e.get("event") == "done")
        assert done["total"] == 3
        assert done["succeeded"] == 3
        assert done["failed"] == 0

    def test_response_content_type_is_event_stream(self, client: TestClient) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
        ):
            response = client.post("/api/settings/bulk/stream-apply", json={"ids": []})

        assert "text/event-stream" in response.headers["content-type"]
        assert response.headers.get("cache-control") == "no-cache"

    def test_missing_ids_field_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/settings/bulk/stream-apply", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/settings/bulk/stream-reset
# ---------------------------------------------------------------------------


class TestBulkStreamReset:
    """Tests for POST /api/settings/bulk/stream-reset."""

    def test_empty_ids_returns_done(self, client: TestClient) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
        ):
            response = client.post("/api/settings/bulk/stream-reset", json={"ids": []})

        assert response.status_code == 200
        events = _parse_sse(response.text)
        done = next((e for e in events if e.get("event") == "done"), None)
        assert done is not None
        assert done["total"] == 0

    def test_successful_reset_emits_applied_and_verified(self, client: TestClient) -> None:
        setting = _make_setting("core:game_mode", recommended_value="1", default_value="0")
        reset_resp = _make_apply_response(success=True, new_value="0")

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch(
                "fpstune.api.routes.settings_stream._reset_single_setting",
                return_value=(setting, reset_resp),
            ),
        ):
            response = client.post(
                "/api/settings/bulk/stream-reset",
                json={"ids": ["core:game_mode"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        event_types = [e.get("event") for e in events]
        assert "applied" in event_types
        assert "verified" in event_types

        done = next(e for e in events if e.get("event") == "done")
        assert done["succeeded"] == 1
        assert done["failed"] == 0

    def test_unknown_id_yields_failed(self, client: TestClient) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
        ):
            response = client.post(
                "/api/settings/bulk/stream-reset",
                json={"ids": ["ghost:setting"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        failed = [e for e in events if e.get("event") == "failed"]
        assert len(failed) == 1
        assert failed[0]["id"] == "ghost:setting"

    def test_missing_ids_field_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/settings/bulk/stream-reset", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# NVIDIA settings take the same per-setting path as every other setting
# ---------------------------------------------------------------------------


class TestNvidiaSettingsAreNotBatched:
    """NVIDIA settings used to be pooled into one nvidiaProfileInspector call
    that skipped the operation lock, value validation and per-setting results.
    Each is now one driver write through the path every setting takes."""

    def test_nvidia_setting_runs_through_the_single_setting_apply(self, client: TestClient) -> None:
        setting = _make_setting(
            "gpu-nvidia:low_latency",
            apply_type_value="nvprofile",
            recommended_value="on",
            default_value="off",
        )
        setting.is_action = False
        apply_resp = _make_apply_response(success=True, new_value="on")
        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch(
                "fpstune.api.routes.settings_stream._apply_single_setting",
                return_value=(setting, apply_resp),
            ) as single,
        ):
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["gpu-nvidia:low_latency"]},
            )

        events = _parse_sse(response.text)
        single.assert_called_once()
        assert single.call_args.args[1] == "on"
        done = next(e for e in events if e.get("event") == "done")
        assert (done["succeeded"], done["failed"]) == (1, 0)

    def test_one_failing_nvidia_setting_does_not_fail_its_neighbours(
        self, client: TestClient
    ) -> None:
        ok = _make_setting("gpu-nvidia:vsync", apply_type_value="nvprofile")
        bad = _make_setting("gpu-nvidia:vrr_mode", apply_type_value="nvprofile")
        mock_registry = MagicMock()
        mock_registry.get.side_effect = lambda sid: {
            "gpu-nvidia:vsync": ok,
            "gpu-nvidia:vrr_mode": bad,
        }[sid]

        def apply(setting, *_a, **_k):
            if setting is bad:
                return setting, _make_apply_response(success=False, error="driver refused")
            return setting, _make_apply_response(success=True, new_value="1")

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings_stream._apply_single_setting", side_effect=apply),
        ):
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["gpu-nvidia:vsync", "gpu-nvidia:vrr_mode"]},
            )

        events = _parse_sse(response.text)
        failed = [e for e in events if e.get("event") == "failed"]
        assert [e["id"] for e in failed] == ["gpu-nvidia:vrr_mode"]
        done = next(e for e in events if e.get("event") == "done")
        assert (done["succeeded"], done["failed"]) == (1, 1)

    def test_the_batch_entry_point_is_gone(self) -> None:
        from fpstune.settings.executors.nvprofile import NvProfileExecutor

        assert not hasattr(NvProfileExecutor, "apply_bulk")
