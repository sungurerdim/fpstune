"""Reset, undo and verify each have to answer a different question.

Three operations were doing two-and-a-half jobs between them:

  ``reset``  writes the curated Windows stock value. Useful, and not the same as
             undoing fpstune — on a machine that deliberately ran something
             non-stock, a reset discards the user's own configuration.
  ``undo``   did not exist. Nothing anywhere recorded what the machine held
             before fpstune changed it; ``safety/`` had System Restore points,
             which are whole-machine.
  ``verify`` always compared against ``recommended_value`` and never said so, so
             a setting correctly sitting at its default after a reset reported
             ``matches=false`` as though the reset had failed.

The apply and reset responses were never wrong about verification — they check
against whatever they wrote. Only the standalone endpoint had one fixed idea of
what "correct" meant.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.api.schemas import ApplyResponse
from fpstune.safety.originals import OriginalValues
from fpstune.settings.base import DetectionResult


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def store(tmp_path) -> OriginalValues:
    return OriginalValues(path=tmp_path / "originals.json")


def _fake_setting(setting_id: str = "core:fake"):
    s = MagicMock()
    s.id = setting_id
    s.display_name = "Fake"
    s.default_value = "stock"
    s.recommended_value = "tuned"
    s.requires_reboot = False
    s.apply_type = MagicMock()
    s.apply_type.value = "registry"
    s.apply_args = {}
    return s


def _detection(value, *, applicable: bool = True, error: str | None = None) -> DetectionResult:
    return DetectionResult(
        setting_id="core:fake",
        value=value,
        error=error,
        time_ms=1,
        is_optimized=False,
        is_applicable=applicable,
    )


class TestVerifyAnswersTheQuestionItWasAsked:
    def _verify(self, client, store, detected, body=None):
        # The store is always the test's own temp one — never the real
        # ~/.fpstune, which a test must not read from or write to.
        setting = _fake_setting()
        registry = MagicMock()
        registry.get.return_value = setting
        originals = store

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch("fpstune.api.routes.settings._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings.get_original_values", return_value=originals),
            patch(
                "fpstune.api.routes.settings.DetectionEngine.detect_one",
                return_value=_detection(detected),
            ),
        ):
            return client.post("/api/settings/core:fake/verify", json=body)

    def test_it_still_defaults_to_the_recommendation(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        """The old behaviour is the default, so existing callers are unaffected."""
        result = self._verify(client, store, "tuned")

        assert result.status_code == 200
        assert result.json()["matches"] is True
        assert result.json()["expected_value"] == "tuned"
        assert result.json()["target"] == "recommended"

    def test_a_reset_setting_no_longer_reads_as_a_failed_operation(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        """The defect, exactly.

        After a reset the setting correctly holds "stock". Asked the default
        question it is drifted from the recommendation, which is true and is not
        what the caller wanted to know; asked about the default it matches.
        """
        drifted = self._verify(client, store, "stock")
        assert drifted.json()["matches"] is False, "it is genuinely not at the recommendation"

        landed = self._verify(client, store, "stock", body={"target": "default"})
        assert landed.json()["matches"] is True, "the reset did land, and verify must say so"
        assert landed.json()["expected_value"] == "stock"
        assert landed.json()["target"] == "default"

    def test_it_can_be_asked_whether_an_undo_landed(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        store.record_first_seen({"core:fake": "what the user had"})

        result = self._verify(client, store, "what the user had", body={"target": "original"})

        assert result.json()["matches"] is True
        assert result.json()["expected_value"] == "what the user had"
        assert result.json()["target"] == "original"

    def test_asking_about_an_unrecorded_original_is_refused(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        """Silently comparing against the default instead would be the same
        conflation this whole change exists to end."""
        result = self._verify(client, store, "anything", body={"target": "original"})

        assert result.status_code == 409
        assert "no record" in result.json()["detail"]

    def test_an_unreadable_setting_still_names_the_question(self, client: TestClient) -> None:
        """A caller must be able to tell which comparison it did not get."""
        setting = _fake_setting()
        registry = MagicMock()
        registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch("fpstune.api.routes.settings._get_hardware_context", return_value=None),
            patch(
                "fpstune.api.routes.settings.DetectionEngine.detect_one",
                return_value=_detection(None, error="timed out"),
            ),
        ):
            result = client.post("/api/settings/core:fake/verify", json={"target": "default"})

        body = result.json()
        assert body["matches"] is False
        assert body["target"] == "default"
        assert body["expected_value"] == "stock"
        assert body["error"] == "timed out"

    def test_a_target_it_does_not_know_is_rejected(self, client: TestClient) -> None:
        result = client.post("/api/settings/core:fake/verify", json={"target": "whatever"})
        assert result.status_code == 422


class TestUndoWritesWhatTheMachineHeld:
    def _undo(self, client, store, *, applied=(True, None), success=True):
        setting = _fake_setting()
        registry = MagicMock()
        registry.get.return_value = setting

        response_obj = ApplyResponse(
            setting_id=setting.id,
            success=success,
            error=None if success else "write failed",
            new_value="what the user had",
            requires_reboot=False,
            verified=success,
        )
        applied_values: list = []

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch("fpstune.api.routes.settings._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings.get_original_values", return_value=store),
            patch(
                "fpstune.api.routes.settings.CommandExecutor.apply",
                side_effect=lambda _s, v: (applied_values.append(v), applied)[1],
            ),
            patch(
                "fpstune.api.routes.settings._finalize_apply_response",
                return_value=response_obj,
            ),
            patch("fpstune.api.routes.settings.sys.platform", "win32"),
            patch("fpstune.api.routes.settings._create_restore_point_async"),
        ):
            result = client.post("/api/settings/core:fake/undo")
        return result, applied_values

    def test_it_writes_the_recorded_value_not_the_default(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        """The distinction the endpoint exists for. `default_value` is "stock"."""
        store.record_first_seen({"core:fake": "what the user had"})

        result, applied = self._undo(client, store)

        assert result.status_code == 200
        assert applied == ["what the user had"], (
            "undo wrote the stock default, which is a reset wearing the wrong name"
        )

    def test_nothing_recorded_is_refused_rather_than_turned_into_a_reset(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        result, applied = self._undo(client, store)

        assert result.status_code == 409
        assert applied == [], "nothing may be written when there is nothing to restore"

    def test_a_landed_undo_frees_the_record(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        store.record_first_seen({"core:fake": "what the user had"})

        self._undo(client, store)

        assert store.has("core:fake") is False, (
            "keeping it would pin a value from an arbitrarily old session and stop "
            "the next scan recording a fresh one"
        )

    def test_a_failed_undo_keeps_the_record_so_it_can_be_retried(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        store.record_first_seen({"core:fake": "what the user had"})

        self._undo(client, store, success=False)

        assert store.get("core:fake") == "what the user had"

    def test_it_creates_a_restore_point_like_apply_and_reset(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        """Undo mutates system state, so it carries the same safety net."""
        store.record_first_seen({"core:fake": "what the user had"})
        setting = _fake_setting()
        registry = MagicMock()
        registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch("fpstune.api.routes.settings._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings.get_original_values", return_value=store),
            patch("fpstune.api.routes.settings.CommandExecutor.apply", return_value=(True, None)),
            patch(
                "fpstune.api.routes.settings._finalize_apply_response",
                return_value=ApplyResponse(
                    setting_id="core:fake",
                    success=True,
                    error=None,
                    new_value="what the user had",
                    requires_reboot=False,
                    verified=True,
                ),
            ),
            patch("fpstune.api.routes.settings.sys.platform", "win32"),
            patch("fpstune.api.routes.settings._create_restore_point_async") as restore_point,
        ):
            client.post("/api/settings/core:fake/undo")

        restore_point.assert_called_once()

    def test_an_unknown_setting_is_a_404(self, client: TestClient) -> None:
        registry = MagicMock()
        registry.get.return_value = None
        with patch("fpstune.api.routes.settings._get_registry", return_value=registry):
            assert client.post("/api/settings/core:nope/undo").status_code == 404


class TestScanRecordsWhatItSaw:
    def test_only_readable_applicable_settings_are_recorded(self, tmp_path) -> None:
        """A None value or an inapplicable setting has no original to record."""
        from fpstune.api.routes.settings import _record_originals

        store = OriginalValues(path=tmp_path / "originals.json")
        results = {
            "a:read": DetectionResult("a:read", "value", None, 1, False, True),
            "b:absent": DetectionResult("b:absent", None, None, 1, False, False),
            "c:errored": DetectionResult("c:errored", None, "boom", 1, False, True),
        }

        with patch("fpstune.api.routes.settings.get_original_values", return_value=store):
            _record_originals(results)

        assert store.get("a:read") == "value"
        assert store.has("b:absent") is False
        assert store.has("c:errored") is False

    def test_a_broken_store_does_not_fail_the_scan(self) -> None:
        """The user asked for a scan, not for a convenience store."""
        from fpstune.api.routes.settings import _record_originals

        exploding = MagicMock()
        exploding.record_first_seen.side_effect = OSError("disk full")

        with patch("fpstune.api.routes.settings.get_original_values", return_value=exploding):
            _record_originals({"a:read": DetectionResult("a:read", "v", None, 1, False, True)})


class TestASingleRedetectNeverRecords:
    """The read that follows an apply must not become the "original".

    `redetectSettings` — the UI's per-row refresh and its Verify button — hits
    the single-detect route, and it runs *after* a write. Recording there would
    capture the value fpstune had just applied, and undo would then re-apply the
    tweak it exists to remove. Originals come from the full scan, which runs
    before the user can apply anything.
    """

    def test_the_single_detect_route_only_reads_the_store(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        setting = _fake_setting()
        registry = MagicMock()
        registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch("fpstune.api.routes.settings._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings.get_original_values", return_value=store),
            patch(
                "fpstune.api.routes.settings.DetectionEngine.detect_one",
                return_value=_detection("value fpstune just wrote"),
            ),
        ):
            result = client.get("/api/settings/detect/core:fake")

        assert result.status_code == 200
        assert store.has("core:fake") is False, (
            "the post-apply read was recorded as the original; undo would now "
            "re-apply the very tweak it is supposed to remove"
        )
        assert result.json()["original_value"] is None

    def test_it_reports_an_original_the_full_scan_did_record(
        self, client: TestClient, store: OriginalValues
    ) -> None:
        store.record_first_seen({"core:fake": "what the user had"})
        setting = _fake_setting()
        registry = MagicMock()
        registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch("fpstune.api.routes.settings._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings.get_original_values", return_value=store),
            patch(
                "fpstune.api.routes.settings.DetectionEngine.detect_one",
                return_value=_detection("tuned"),
            ),
        ):
            result = client.get("/api/settings/detect/core:fake")

        assert result.json()["original_value"] == "what the user had"
