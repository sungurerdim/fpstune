"""Consent path for the 1.3 GB test-scene download.

`GpuSceneBench.allow_download` stays False on every automatic run (C11 rule 3:
fpstune never spends somebody's line unasked), so the only way the scene is
ever installed is a user's own button press landing on these two routes.
These tests hold the HTTP layer to that contract without touching the
network, a real 1.3 GB file, or a real Windows mutex another test might hold.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.benchmark.gpu_scene import GpuSceneBench


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


class TestGpuSceneStatus:
    def test_reports_not_installed_and_what_it_costs(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The panel has to say the size and the licence *before* the button is
        pressed, so consent happens on this screen and not inside the download."""
        monkeypatch.setattr(GpuSceneBench, "is_installed", lambda _self: False)

        payload = client.get("/api/benchmark/gpu-scene").json()

        assert payload["installed"] is False
        assert payload["download_size"] == "1.3 GB"
        assert "Superposition Basic" in payload["licence_note"]
        assert "Unigine's own server" in payload["licence_note"]

    def test_reports_installed_once_it_is(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(GpuSceneBench, "is_installed", lambda _self: True)

        payload = client.get("/api/benchmark/gpu-scene").json()

        assert payload["installed"] is True


class TestGpuSceneInstall:
    def test_a_successful_install_reports_installed_with_no_reason(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(GpuSceneBench, "install", lambda _self: True)

        payload = client.post("/api/benchmark/gpu-scene/install").json()

        assert payload == {"installed": True, "reason": ""}

    def test_a_failed_install_reports_the_benchs_own_reason(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """C11 rule 3: a failure is a sentence, not a bare False."""

        def fail(self: GpuSceneBench) -> bool:
            self._install_error = (
                "the download is 512 bytes and the pinned installer is "
                "1339177360, so it was deleted unrun"
            )
            return False

        monkeypatch.setattr(GpuSceneBench, "install", fail)

        payload = client.post("/api/benchmark/gpu-scene/install").json()

        assert payload["installed"] is False
        assert "1339177360" in payload["reason"]

    def test_refuses_while_another_operation_holds_the_machine(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bench mid-run or a bulk apply already holds `operation_lock`; the
        install has to say so at once (409) rather than silently queue behind
        it or start writing to disk underneath another operation."""

        @contextlib.contextmanager
        def refused(*_args: Any, **_kwargs: Any):
            yield False

        monkeypatch.setattr("fpstune.benchmark.operation_lock.operation_lock", refused)
        monkeypatch.setattr(
            GpuSceneBench, "install", lambda _self: pytest.fail("must not install while busy")
        )

        response = client.post("/api/benchmark/gpu-scene/install")

        assert response.status_code == 409
        assert "1.3 GB" in response.json()["detail"]
