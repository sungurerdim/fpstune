"""Verify has to answer the question it was asked: recommended or default.

``verify`` always compared against ``recommended_value`` and never said so, so
a setting correctly sitting at its default after a reset reported
``matches=false`` as though the reset had failed. ``target`` names the question
and the answer echoes it back. fpstune stores no previous values (#103), so
``original`` is not a question it can answer and is rejected.

The apply and reset responses were never wrong about verification — they check
against whatever they wrote. Only the standalone endpoint had one fixed idea of
what "correct" meant.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.settings.base import DetectionResult
from tests.conftest import neutral_hardware_context


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


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
    s.is_action = False
    s.is_readonly = False
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
    def _verify(self, client, detected, body=None):
        setting = _fake_setting()
        registry = MagicMock()
        registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch(
                "fpstune.api.routes.settings._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
            patch(
                "fpstune.api.routes.settings.DetectionEngine.detect_one",
                return_value=_detection(detected),
            ),
        ):
            return client.post("/api/settings/core:fake/verify", json=body)

    def test_it_still_defaults_to_the_recommendation(self, client: TestClient) -> None:
        """The old behaviour is the default, so existing callers are unaffected."""
        result = self._verify(client, "tuned")

        assert result.status_code == 200
        assert result.json()["matches"] is True
        assert result.json()["expected_value"] == "tuned"
        assert result.json()["target"] == "recommended"

    def test_a_reset_setting_no_longer_reads_as_a_failed_operation(
        self, client: TestClient
    ) -> None:
        """The defect, exactly.

        After a reset the setting correctly holds "stock". Asked the default
        question it is drifted from the recommendation, which is true and is not
        what the caller wanted to know; asked about the default it matches.
        """
        drifted = self._verify(client, "stock")
        assert drifted.json()["matches"] is False, "it is genuinely not at the recommendation"

        landed = self._verify(client, "stock", body={"target": "default"})
        assert landed.json()["matches"] is True, "the reset did land, and verify must say so"
        assert landed.json()["expected_value"] == "stock"
        assert landed.json()["target"] == "default"

    def test_an_unreadable_setting_still_names_the_question(self, client: TestClient) -> None:
        """A caller must be able to tell which comparison it did not get."""
        setting = _fake_setting()
        registry = MagicMock()
        registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch(
                "fpstune.api.routes.settings._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
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

    def test_the_retired_original_target_is_rejected(self, client: TestClient) -> None:
        """fpstune keeps no previous values, so there is nothing to compare against."""
        result = client.post("/api/settings/core:fake/verify", json={"target": "original"})
        assert result.status_code == 422
