"""The support log is readable from the UI: path, summary and a bounded tail."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_diagnostics_returns_the_log_tail(test_client: TestClient, tmp_path: Path) -> None:
    log = tmp_path / "operations.log"
    log.write_text("header\nAPPLY | ok | one\nAPPLY | failed | two\n", encoding="utf-8")
    with (
        patch("fpstune.api.routes.system.operation_log.path", log),
        patch("fpstune.api.routes.system.operation_log.summary", return_value="ok=1, failed=1"),
    ):
        response = test_client.get("/api/system/diagnostics?lines=2")

    assert response.status_code == 200
    body = response.json()
    assert body["log_path"] == str(log)
    assert body["exists"] is True
    assert body["summary"] == "ok=1, failed=1"
    assert body["lines"] == ["APPLY | ok | one", "APPLY | failed | two"]
    assert body["generated_at"]


def test_diagnostics_says_when_the_log_does_not_exist(
    test_client: TestClient, tmp_path: Path
) -> None:
    missing = tmp_path / "missing.log"
    with patch("fpstune.api.routes.system.operation_log.path", missing):
        response = test_client.get("/api/system/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is False
    assert body["lines"] == []
