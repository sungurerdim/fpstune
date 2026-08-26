"""The sweep, reachable from outside the process.

The engine's own guards live in tests/test_settings/test_config_sweep.py. What
matters here is that the HTTP layer does not quietly change the promise: that it
reports by default rather than writing, and that asking it to write is a
deliberate act rather than the shape of the URL.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.settings.executors import config_sweep


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def _block(marker: str, body: str) -> str:
    return f"// ===fpstune-{marker}-start===\n{body}\n// ===fpstune-{marker}-end===\n"


@pytest.fixture
def staged(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    target = tmp_path / "autoexec.cfg"
    target.write_text(
        _block("cs2_autohelp", "cl_autohelp 0")
        + "\n"
        + _block("snd_mixahead", "snd_mixahead 0.05"),
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(config_sweep, "cs2_autoexec_path", lambda: target)
    return target


class TestTheRouteReportsBeforeItWrites:
    def test_the_default_is_a_report(self, client: TestClient, staged: pathlib.Path) -> None:
        # A sweep that wrote on a plain POST would edit a file the user may also
        # have edited by hand, without them having asked for it.
        before = staged.read_bytes()
        payload = client.post("/api/settings/game-configs/sweep").json()

        assert payload["status"] == "would_remove"
        assert payload["orphaned"] == ["snd_mixahead"]
        assert payload["removed"] == []
        assert staged.read_bytes() == before

    def test_writing_has_to_be_asked_for(self, client: TestClient, staged: pathlib.Path) -> None:
        payload = client.post("/api/settings/game-configs/sweep?apply=true").json()

        assert payload["removed"] == ["snd_mixahead"]
        assert payload["backup"]
        text = staged.read_text(encoding="utf-8-sig")
        assert "snd_mixahead" not in text
        assert "cl_autohelp 0" in text, "a live block went with the orphan"

    def test_a_missing_game_is_not_an_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No CS2 means nothing to sweep, which is an answer rather than a fault.
        monkeypatch.setattr(config_sweep, "cs2_autoexec_path", lambda: None)
        response = client.post("/api/settings/game-configs/sweep")

        assert response.status_code == 200
        assert response.json()["status"] == "not_installed"

    def test_the_route_does_not_collide_with_a_setting_id(self, client: TestClient) -> None:
        # `/settings/{setting_id}/apply` sits in the same router and has the same
        # shape. This proves the sweep is reached rather than being read as a
        # setting called "game-configs".
        response = client.post("/api/settings/game-configs/sweep")

        assert response.status_code == 200
        assert "orphaned" in response.json()
