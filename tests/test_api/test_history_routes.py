"""The history page reads one row per changed setting and can undo in bulk."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.safety.history import get_change_journal
from fpstune.safety.originals import get_original_values


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_one_row_per_setting_newest_first_with_its_undo_state(client: TestClient) -> None:
    journal = get_change_journal()
    journal.record("network:nagle_algorithm", "apply", "disabled")
    journal.record("system:game_mode", "apply", "enabled")
    journal.record("network:nagle_algorithm", "reset", "enabled")
    get_original_values().record_first_seen({"system:game_mode": "disabled"})

    body = client.get("/api/history").json()

    assert [r["setting_id"] for r in body["settings"]] == [
        "network:nagle_algorithm",
        "system:game_mode",
    ]
    nagle, game_mode = body["settings"]
    assert (nagle["last_action"], nagle["can_undo"]) == ("reset", False)
    assert (game_mode["can_undo"], game_mode["original_value"]) == (True, "disabled")
    assert len(body["entries"]) == 3


def test_bulk_undo_without_a_record_fails_with_the_reason_never_resets(
    client: TestClient,
) -> None:
    """Undo and reset are two promises (C6): no record means no undo, not a reset."""
    with patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None):
        response = client.post(
            "/api/settings/bulk/stream-undo", json={"ids": ["network:nagle_algorithm"]}
        )

    events = [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    failed = [e for e in events if e.get("event") == "failed"]
    assert failed and "no record" in failed[0]["error"]
    assert events[-1]["event"] == "done" and events[-1]["failed"] == 1
