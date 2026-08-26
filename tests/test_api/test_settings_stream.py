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
# NVPROFILE batch path
# ---------------------------------------------------------------------------


def _real_nvprofile_setting():
    """A real SettingExecutor — MagicMock would make is_action/is_readonly
    truthy and silently skip the very verification these tests assert on."""
    from fpstune.settings.base import (
        DetectType,
        SettingCategory,
        SettingExecutor,
        SettingValueType,
    )

    return SettingExecutor(
        id="gpu-nvidia:low_latency",
        category=SettingCategory.GPU,
        display_name="Low Latency Mode",
        description="NVIDIA Reflex / Ultra Low Latency mode.",
        value_type=SettingValueType.CHOICE,
        choices=("off", "on", "ultra"),
        default_value="off",
        recommended_value="on",
        detect_type=DetectType.NVPROFILE,
        detect_command="",
        detect_args={"setting": "low_latency"},
        apply_type=DetectType.NVPROFILE,
        apply_command="",
        apply_args={"setting": "low_latency"},
    )


class TestNvprofileVerificationIsReal:
    """The NVIDIA batch previously emitted matches=True with the *requested*
    value without ever reading anything back.

    It now performs a real read-back. The verdict is still reported as unknown,
    because NVIDIA detection currently reads fpstune's own cache — but the
    reported value must come from the read-back, and the stream must never
    claim a check it did not perform.
    """

    def test_requested_value_is_never_echoed_as_the_result(self, client: TestClient) -> None:
        setting = _real_nvprofile_setting()

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        # NPI reports success, but the value read back is still the old one.
        stale = MagicMock()
        stale.value = "off"
        mock_engine = MagicMock()
        mock_engine.detect_one.return_value = stale

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings_stream.DetectionEngine", return_value=mock_engine),
            patch("fpstune.settings.executors.nvprofile.NvProfileExecutor") as mock_nv_cls,
        ):
            mock_nv_cls.apply_bulk.return_value = (True, None)
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["gpu-nvidia:low_latency"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        verified = next(e for e in events if e.get("event") == "verified")
        # "on" was requested; the read-back said "off" — the request must not
        # be presented as the outcome.
        assert verified["current_value"] == "off"
        assert verified["matches"] is not True
        mock_engine.detect_one.assert_called_once()

    def test_readback_match_is_verified_with_detected_value(self, client: TestClient) -> None:
        setting = _real_nvprofile_setting()

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        fresh = MagicMock()
        fresh.value = "on"
        mock_engine = MagicMock()
        mock_engine.detect_one.return_value = fresh

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings_stream.DetectionEngine", return_value=mock_engine),
            patch("fpstune.settings.executors.nvprofile.NvProfileExecutor") as mock_nv_cls,
        ):
            mock_nv_cls.apply_bulk.return_value = (True, None)
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["gpu-nvidia:low_latency"]},
            )

        events = _parse_sse(response.text)
        verified = next(e for e in events if e.get("event") == "verified")
        # The reported value must come from the read-back, not the request.
        assert verified["current_value"] == "on"
        # Still unknown rather than True: NVIDIA detection reads fpstune's own
        # cache, so a match proves nothing about the driver.
        assert verified["matches"] is None
        mock_engine.detect_one.assert_called_once()


class TestNvprofileBatchPath:
    """Tests for the NVPROFILE group handling in _stream_grouped."""

    def test_nvprofile_settings_use_bulk_apply(self, client: TestClient) -> None:
        """NVPROFILE settings must be grouped into a single NPI call."""
        setting = _make_setting(
            "gpu-nvidia:low_latency",
            apply_type_value="nvprofile",
            recommended_value="ultra",
        )
        setting.apply_args = {"setting": "low_latency"}

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch("fpstune.settings.executors.nvprofile.NvProfileExecutor") as mock_nv_cls,
        ):
            mock_nv_cls.apply_bulk.return_value = (True, None)
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["gpu-nvidia:low_latency"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        done = next(e for e in events if e.get("event") == "done")
        assert done["succeeded"] == 1
        assert done["failed"] == 0
        # Bulk apply was called once (not per-setting subprocess)
        mock_nv_cls.apply_bulk.assert_called_once()

    def test_nvprofile_bulk_failure_emits_failed_for_each(self, client: TestClient) -> None:
        setting = _make_setting(
            "gpu-nvidia:vsync",
            apply_type_value="nvprofile",
            recommended_value="off",
        )
        setting.apply_args = {"setting": "vsync"}

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch("fpstune.settings.executors.nvprofile.NvProfileExecutor") as mock_nv_cls,
        ):
            mock_nv_cls.apply_bulk.return_value = (False, "NPI not found")
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["gpu-nvidia:vsync"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        failed = [e for e in events if e.get("event") == "failed"]
        assert len(failed) == 1
        assert "NPI not found" in failed[0]["error"]

        done = next(e for e in events if e.get("event") == "done")
        assert done["failed"] == 1
        assert done["succeeded"] == 0


class TestNvprofileBatchGoesThroughFinalize:
    """ARCH-12 regression: the NVIDIA batch verified inline and bypassed
    _finalize_apply_response — no log_activity, no ApplicabilityChecker, no
    cleanup-cache invalidation, so bulk-applied NVIDIA tweaks never appeared in
    the Activity drawer.
    """

    def test_batch_apply_logs_an_activity_entry(self, client: TestClient) -> None:
        setting = _real_nvprofile_setting()

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        fresh = MagicMock()
        fresh.value = "on"
        mock_engine = MagicMock()
        mock_engine.detect_one.return_value = fresh

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings_stream.DetectionEngine", return_value=mock_engine),
            patch("fpstune.settings.executors.nvprofile.NvProfileExecutor") as mock_nv_cls,
            patch("fpstune.api.routes.settings.log_activity") as mock_log,
        ):
            mock_nv_cls.apply_bulk.return_value = (True, None)
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["gpu-nvidia:low_latency"]},
            )

        assert response.status_code == 200
        messages = [call.args[0] for call in mock_log.call_args_list]
        assert any("Low Latency Mode" in message for message in messages), (
            "the NVIDIA batch apply left no Activity entry"
        )

    def test_apply_skips_an_inapplicable_setting_without_writing(self, client: TestClient) -> None:
        setting = _real_nvprofile_setting()

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        checker = MagicMock()
        checker.is_applicable.return_value = (False, "No NVIDIA GPU detected")

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch(
                "fpstune.api.routes.settings_stream._get_hardware_context",
                return_value=MagicMock(),
            ),
            patch("fpstune.api.routes.settings_stream.ApplicabilityChecker", return_value=checker),
            patch("fpstune.settings.executors.nvprofile.NvProfileExecutor") as mock_nv_cls,
        ):
            mock_nv_cls.apply_bulk.return_value = (True, None)
            response = client.post(
                "/api/settings/bulk/stream-apply",
                json={"ids": ["gpu-nvidia:low_latency"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        skipped = [e for e in events if e.get("event") == "skipped"]
        assert len(skipped) == 1
        # The old path wrote first and asked never: the NPI call must not run
        # for a setting the hardware cannot hold.
        mock_nv_cls.apply_bulk.assert_not_called()

        done = next(e for e in events if e.get("event") == "done")
        assert done["succeeded"] == 1
        assert done["failed"] == 0

    def test_reset_reports_an_inapplicable_setting_as_failed(self, client: TestClient) -> None:
        setting = _real_nvprofile_setting()

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        checker = MagicMock()
        checker.is_applicable.return_value = (False, "No NVIDIA GPU detected")

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch(
                "fpstune.api.routes.settings_stream._get_hardware_context",
                return_value=MagicMock(),
            ),
            patch("fpstune.api.routes.settings_stream.ApplicabilityChecker", return_value=checker),
            patch("fpstune.settings.executors.nvprofile.NvProfileExecutor") as mock_nv_cls,
        ):
            mock_nv_cls.apply_bulk.return_value = (True, None)
            response = client.post(
                "/api/settings/bulk/stream-reset",
                json={"ids": ["gpu-nvidia:low_latency"]},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        failed = [e for e in events if e.get("event") == "failed"]
        assert len(failed) == 1
        assert "No NVIDIA GPU detected" in failed[0]["error"]
        mock_nv_cls.apply_bulk.assert_not_called()
