"""The history page reads one row per setting changed this session, from memory."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.safety.history import get_change_journal


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_one_row_per_setting_newest_first(client: TestClient) -> None:
    journal = get_change_journal()
    journal.record("network:nagle_algorithm", "apply", "disabled")
    journal.record("network:tcp_auto_tuning", "apply", "enabled")
    journal.record("network:nagle_algorithm", "reset", "enabled")

    body = client.get("/api/history").json()

    assert [r["setting_id"] for r in body["settings"]] == [
        "network:nagle_algorithm",
        "network:tcp_auto_tuning",
    ]
    nagle, auto_tuning = body["settings"]
    assert (nagle["last_action"], nagle["value"]) == ("reset", "enabled")
    assert auto_tuning["last_action"] == "apply"
    assert len(body["entries"]) == 3


def test_a_row_carries_no_previous_value_and_no_undo_state(client: TestClient) -> None:
    """fpstune stores no previous values (#103): nothing to offer an undo from."""
    get_change_journal().record("network:nagle_algorithm", "apply", "disabled")

    row = client.get("/api/history").json()["settings"][0]

    assert set(row) == {"setting_id", "last_action", "value", "at"}


def test_a_fresh_process_has_an_empty_history(client: TestClient) -> None:
    body = client.get("/api/history").json()

    assert body == {"settings": [], "entries": []}


def test_the_undo_endpoints_are_gone(client: TestClient) -> None:
    assert client.post("/api/settings/network:nagle_algorithm/undo").status_code in (404, 405)
    assert client.post("/api/settings/bulk/stream-undo", json={"ids": []}).status_code in (
        404,
        405,
        422,
    )
