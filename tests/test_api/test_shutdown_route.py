"""POST /api/system/shutdown: how a newer fpstune start closes the one it replaces.

Each test names what it guards:

* a refused request must not stop anything (a web page stopping an elevated
  instance it does not own),
* the stop must be the server's own graceful one — the lifespan's shutdown path
  runs — and never a kill,
* an apply, cleanup or bench holding the operation lock is waited for, not cut
  off, and the wait is bounded.

Nothing here terminates a process: the "server" is either a recording hook or a
small uvicorn server on a free port that stops itself.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
import urllib.request
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fpstune.api import shutdown
from fpstune.api.main import create_app
from fpstune.api.routes import system_router
from fpstune.api.serving import run_api
from fpstune.benchmark import operation_lock
from fpstune.utils import instances


@pytest.fixture(autouse=True)
def _fresh_shutdown_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stop request and its hook are process state; no test inherits another's."""
    monkeypatch.setattr(shutdown, "_pending", False)
    monkeypatch.setattr(shutdown, "_stop_server", None)
    monkeypatch.setattr(shutdown, "_POLL_SECONDS", 0.01)


class _Hook:
    """A stop hook that records that it ran, in order with the lock being given back."""

    def __init__(self, order: list[str]) -> None:
        self.calls = 0
        self._order = order

    def __call__(self) -> None:
        self.calls += 1
        self._order.append("stopped")


@pytest.fixture
def order() -> list[str]:
    return []


@pytest.fixture
def hook(order: list[str]) -> _Hook:
    recorded = _Hook(order)
    shutdown.install_stop_hook(recorded)
    return recorded


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


class _HeldOperation:
    """The machine-wide operation lock, held by another thread like a running apply.

    The Windows mutex belongs to the thread that took it, so the holder is a
    thread of its own that takes it and gives it back on request.
    """

    def __init__(self, order: list[str]) -> None:
        self._order = order
        self._taken = threading.Event()
        self._give_back = threading.Event()
        self._thread = threading.Thread(target=self._hold, daemon=True)

    def _hold(self) -> None:
        held = operation_lock.try_acquire()
        if held is None:
            return
        self._taken.set()
        self._give_back.wait()
        self._order.append("released")
        held.release()

    def __enter__(self) -> _HeldOperation:
        self._thread.start()
        assert self._taken.wait(5), "the test could not take the operation lock"
        return self

    def release(self) -> None:
        self._give_back.set()
        self._thread.join(5)

    def __exit__(self, *_exc: object) -> None:
        self.release()


class TestTheRequestIsAnswered:
    def test_202_and_the_graceful_stop_is_invoked(self, client: TestClient, hook: _Hook) -> None:
        response = client.post("/api/system/shutdown")

        assert response.status_code == 202
        assert response.json()["status"] == "shutting_down"
        assert response.json()["waiting_for_operation"] is False
        assert hook.calls == 1, "the server's own graceful stop was never asked for"

    def test_a_second_request_is_not_a_second_stop(self, client: TestClient, hook: _Hook) -> None:
        client.post("/api/system/shutdown")
        again = client.post("/api/system/shutdown")

        assert again.status_code == 202
        assert again.json()["status"] == "already_requested"
        assert hook.calls == 1

    def test_a_server_fpstune_did_not_start_says_it_cannot_stop(self, client: TestClient) -> None:
        """`uvicorn fpstune.api.main:app` has no hook: promising a stop would be a lie."""
        response = client.post("/api/system/shutdown")

        assert response.status_code == 501
        assert shutdown.is_pending() is False


class TestTheBrowserPerimeterStillGuardsIt:
    def test_a_cross_origin_post_is_refused_and_stops_nothing(
        self, client: TestClient, hook: _Hook
    ) -> None:
        """A hostile page's simple POST is the attack: it must die at the Origin
        check, before the handler could mark a stop pending."""
        response = client.post("/api/system/shutdown", headers={"Origin": "http://evil.example"})

        assert response.status_code == 403
        assert response.json()["detail"] == "Cross-origin request rejected"
        assert hook.calls == 0
        assert shutdown.is_pending() is False

    def test_a_null_origin_is_refused_too(self, client: TestClient, hook: _Hook) -> None:
        response = client.post("/api/system/shutdown", headers={"Origin": "null"})

        assert response.status_code == 403
        assert hook.calls == 0

    def test_a_rebound_dns_name_is_refused(self, client: TestClient, hook: _Hook) -> None:
        response = client.post("/api/system/shutdown", headers={"Host": "rebind.attacker.example"})

        assert response.status_code == 400
        assert hook.calls == 0

    def test_the_servers_own_origin_is_accepted(self, client: TestClient, hook: _Hook) -> None:
        response = client.post("/api/system/shutdown", headers={"Origin": "http://testserver"})

        assert response.status_code == 202
        assert hook.calls == 1


class TestARunningOperationIsWaitedFor:
    def test_the_stop_waits_until_the_operation_lock_is_free(
        self, client: TestClient, hook: _Hook, order: list[str]
    ) -> None:
        """An apply mid-way must not be cut off: the stop fires only after the
        lock is given back, and the response says it is waiting."""
        with _HeldOperation(order) as held:
            releaser = threading.Timer(0.3, held.release)
            releaser.start()
            response = client.post("/api/system/shutdown")
            releaser.join()

        assert response.status_code == 202
        assert response.json()["waiting_for_operation"] is True
        assert response.json()["operation_wait_limit_s"] == shutdown.OPERATION_WAIT_SECONDS
        assert hook.calls == 1
        assert order == ["released", "stopped"], "the server was stopped under a running operation"

    def test_the_wait_is_bounded_and_the_stop_then_goes_ahead(
        self, client: TestClient, hook: _Hook, order: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hung operation must not make the request immortal."""
        monkeypatch.setattr(shutdown, "OPERATION_WAIT_SECONDS", 0.2)
        started = time.monotonic()

        with _HeldOperation(order):
            response = client.post("/api/system/shutdown")
            stopped_while_held = hook.calls

        assert response.status_code == 202
        assert stopped_while_held == 1, "the stop never went ahead after the bound"
        assert time.monotonic() - started >= 0.2, "the stop did not wait at all"

    def test_the_bound_is_sixty_seconds(self) -> None:
        assert shutdown.OPERATION_WAIT_SECONDS == 60.0


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _tiny_fpstune_app(events: list[str]) -> FastAPI:
    """The real system router on an app that records its lifespan, without fpstune's own."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        events.append("startup")
        yield
        events.append("lifespan shutdown")

    app = FastAPI(lifespan=lifespan)
    app.include_router(system_router, prefix="/api")

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    return app


class TestARealServerStopsItself:
    def test_the_request_ends_the_server_through_its_lifespan(self) -> None:
        """End to end on a real uvicorn server: 202 on the wire, the lifespan's
        shutdown path runs, the serving call returns, the port is given back.
        Nothing is killed."""
        events: list[str] = []
        port = _free_port()
        errors: list[BaseException] = []

        def serve() -> None:
            try:
                run_api(port=port, app=_tiny_fpstune_app(events))
            except BaseException as exc:
                errors.append(exc)

        server = threading.Thread(target=serve, daemon=True)
        server.start()
        try:
            deadline = time.monotonic() + 15
            while True:
                with contextlib.suppress(OSError):
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=1).close()
                    break
                assert time.monotonic() < deadline, "the test server never came up"
                time.sleep(0.05)

            assert instances.post_stop(port) == 202
            server.join(15)
        finally:
            shutdown.clear_stop_hook()

        assert not server.is_alive(), "the server ignored the stop request"
        assert errors == []
        assert events == ["startup", "lifespan shutdown"]
        with socket.socket() as again:
            again.bind(("127.0.0.1", port))
