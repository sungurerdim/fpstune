"""Tests for the browser-facing perimeter in api/main.py.

The API binds loopback, runs elevated, and has no authentication by design —
the Host and Origin checks in ``create_app`` are the entire defense against a
hostile web page reaching it. Each test here names the attack (or the
legitimate caller) it pins down.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(create_app())


@pytest.fixture
def frozen_client() -> TestClient:
    """Create test client for an app built as the packaged exe would build it."""
    with patch("fpstune.api.main.is_frozen", return_value=True):
        app = create_app()
    return TestClient(app)


class TestHostHeaderGuard:
    """SEC-18: DNS rebinding — a foreign name resolved to 127.0.0.1 becomes
    same-origin to itself, so CORS never runs; the Host header is the tell."""

    def test_foreign_host_is_rejected(self, client: TestClient) -> None:
        """A rebound DNS name arrives as a non-loopback Host and must be 400."""
        response = client.get("/", headers={"Host": "rebind.attacker.example"})

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid Host header"

    def test_foreign_host_is_rejected_on_writes_too(self, client: TestClient) -> None:
        """The rebinding page's POST must die at the Host check, before routing."""
        response = client.post("/api/settings/detect", headers={"Host": "rebind.attacker.example"})

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "host",
        ["127.0.0.1:8000", "localhost:8000", "127.0.0.1", "localhost", "[::1]:8000"],
    )
    def test_loopback_hosts_are_accepted(self, client: TestClient, host: str) -> None:
        """Every name the local browser can legitimately use keeps working."""
        response = client.get("/", headers={"Host": host})

        assert response.status_code == 200

    def test_testclient_default_host_is_accepted_under_pytest(self, client: TestClient) -> None:
        """TestClient's http://testserver base stays usable for the test suite."""
        response = client.get("/")

        assert response.status_code == 200


class TestCrossOriginWriteGuard:
    """SEC-19: the write endpoints take query/path params only, so a hostile
    page can fire them as CORS-simple requests — the response is opaque but the
    elevated side effect would land. The Origin header is what stops it.

    The tests POST to a path with no route: a 403 proves the guard fired
    before routing (no handler could run), a 404 proves the request passed
    the guard and reached the router.
    """

    def test_cross_origin_post_is_rejected_before_routing(self, client: TestClient) -> None:
        """A hostile page's simple POST must be refused before any handler."""
        response = client.post("/api/no-such-route", headers={"Origin": "http://evil.example"})

        assert response.status_code == 403
        assert response.json()["detail"] == "Cross-origin request rejected"

    def test_null_origin_post_is_rejected(self, client: TestClient) -> None:
        """Origin: null (sandboxed iframe, data: URL) is an unidentifiable
        browser context and gets no write access."""
        response = client.post("/api/no-such-route", headers={"Origin": "null"})

        assert response.status_code == 403

    def test_cross_origin_delete_is_rejected(self, client: TestClient) -> None:
        """The guard covers every state-changing method, not just POST."""
        response = client.delete("/api/no-such-route", headers={"Origin": "http://evil.example"})

        assert response.status_code == 403

    def test_same_origin_post_passes(self, client: TestClient) -> None:
        """The bundled UI at /ui sends its own origin and must keep working."""
        response = client.post("/api/no-such-route", headers={"Origin": "http://testserver"})

        assert response.status_code == 404

    def test_post_without_origin_passes(self, client: TestClient) -> None:
        """Non-browser clients (CLI, tests, curl) send no Origin and are not
        cross-site requests; they must not be locked out."""
        response = client.post("/api/no-such-route")

        assert response.status_code == 404

    def test_cross_origin_get_is_not_blocked(self, client: TestClient) -> None:
        """Reads stay open: without a CORS grant the response is opaque to a
        foreign page, and blocking them would break nothing-to-gain cases."""
        response = client.get("/", headers={"Origin": "http://evil.example"})

        assert response.status_code == 200

    def test_dev_origin_post_allowed_from_source_checkout(self, client: TestClient) -> None:
        """The Vite dev server is cross-origin by construction and must keep
        write access while running from source."""
        response = client.post("/api/no-such-route", headers={"Origin": "http://localhost:5173"})

        assert response.status_code == 404


class TestFrozenBuildSurface:
    """SEC-24: the shipped exe serves its UI same-origin, so any cross-origin
    grant in it hands another local app credentialed access to an elevated API."""

    def test_frozen_build_rejects_dev_origin_writes(self, frozen_client: TestClient) -> None:
        """A page on a dev-server port is just another local app to the exe."""
        response = frozen_client.post(
            "/api/no-such-route", headers={"Origin": "http://localhost:5173"}
        )

        assert response.status_code == 403

    def test_frozen_build_grants_no_cors_origin(self, frozen_client: TestClient) -> None:
        """Preflight from a dev origin must come back with no CORS grant."""
        response = frozen_client.options(
            "/api/status",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert "access-control-allow-origin" not in response.headers

    def test_source_checkout_still_grants_dev_origin(self, client: TestClient) -> None:
        """The same preflight from a source checkout keeps its CORS grant, so
        the dev-server workflow is unchanged."""
        response = client.options(
            "/api/status",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
