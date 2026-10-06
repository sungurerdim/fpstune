"""A newer fpstune start closes the running ones and takes their place.

Two layers. ``utils.instances`` is exercised against real loopback HTTP servers
(what is fpstune, what is not, what a stop request gets back). The start-up flow
in ``cli._claim_single_instance`` runs against a pretend machine: no process
exists, so none can be killed, and the clock is a fake so the bounded waits cost
nothing.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from fpstune import cli
from fpstune.utils import instances


def _fpstune_health() -> dict[str, object]:
    """What a running fpstune's /health answers (api/main.py), field for field."""
    return {
        "status": "healthy",
        "version": "0.3.0",
        "platform": "win32",
        "is_admin": True,
        "subsystems": {"registry": True, "powershell": True, "gpu_detection": "ready"},
    }


# ---------------------------------------------------------------------------
# Identification: what counts as an fpstune, over real HTTP
# ---------------------------------------------------------------------------


@contextmanager
def _server(
    health: object, *, stop_status: int = 202, raw_health: bytes | None = None
) -> Iterator[tuple[int, list[str]]]:
    """A loopback HTTP server answering /health, recording the stop requests it gets."""
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - http.server's naming
            if self.path == instances.HEALTH_PATH:
                self._send(
                    200, raw_health if raw_health is not None else json.dumps(health).encode()
                )
            else:
                self._send(404, b"{}")

        def do_POST(self) -> None:  # noqa: N802
            requests.append(self.path)
            self._send(stop_status, b"{}")

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1]), requests
    finally:
        server.shutdown()
        server.server_close()


class TestAnInstanceIsIdentifiedByItsHealthBodyAlone:
    def test_fpstunes_own_health_is_recognised(self) -> None:
        assert instances.is_fpstune_health(_fpstune_health()) is True
        degraded = {**_fpstune_health(), "status": "degraded"}
        assert instances.is_fpstune_health(degraded) is True

    @pytest.mark.parametrize(
        "body",
        [
            None,
            [],
            "healthy",
            {},
            {"status": "ok"},
            {"status": "healthy", "subsystems": {}},  # the one key the old check looked for
            {**_fpstune_health(), "status": "on fire"},
            {**_fpstune_health(), "version": 3},
            {**_fpstune_health(), "is_admin": "yes"},
            {**_fpstune_health(), "subsystems": {"registry": True}},
            {**_fpstune_health(), "subsystems": ["registry", "powershell", "gpu_detection"]},
        ],
    )
    def test_anything_short_of_the_full_shape_is_not_fpstune(self, body: object) -> None:
        assert instances.is_fpstune_health(body) is False

    def test_a_real_server_with_fpstunes_health_is_found_and_asked_to_stop(self) -> None:
        with _server(_fpstune_health()) as (port, requests):
            assert instances.find_instances([port]) == [port]
            attempts = instances.stop_instances([port])

        assert [a.accepted for a in attempts] == [True]
        assert requests == [instances.SHUTDOWN_PATH]

    def test_a_real_server_that_is_not_fpstune_is_found_by_nothing_and_never_posted_to(
        self,
    ) -> None:
        with (
            _server({"status": "healthy", "subsystems": {}}) as (lookalike, lookalike_posts),
            _server({"anything": "else"}) as (stranger, stranger_posts),
            _server(None, raw_health=b"<html>not json</html>") as (web_page, web_posts),
        ):
            found = instances.find_instances([lookalike, stranger, web_page])

        assert found == []
        assert lookalike_posts == stranger_posts == web_posts == []

    def test_a_port_nothing_listens_on_is_simply_not_an_instance(self) -> None:
        with _server(_fpstune_health()) as (port, _):
            pass  # closed again: the port is now free

        assert instances.find_instances([port]) == []
        assert instances.post_stop(port) is None

    def test_an_older_fpstune_without_the_stop_request_reports_its_refusal(self) -> None:
        with _server(_fpstune_health(), stop_status=404) as (port, _):
            [attempt] = instances.stop_instances([port])

        assert attempt.status == 404 and attempt.accepted is False
        assert "refused (HTTP 404" in attempt.describe()

    def test_the_scan_covers_the_pid_file_port_then_the_serve_range_without_repeats(self) -> None:
        ports = instances.candidate_ports(8000, 8003)

        assert ports[0] == 8003
        assert ports[1:] == [8000, 8001, 8002, 8004, 8005, 8006, 8007, 8008, 8009]

    def test_a_pid_file_port_outside_the_range_is_added_and_a_bogus_one_is_dropped(self) -> None:
        assert instances.candidate_ports(8000, 9123)[0] == 9123
        assert 70000 not in instances.candidate_ports(8000, 70000)
        assert instances.candidate_ports(8000, None) == list(range(8000, 8010))


# ---------------------------------------------------------------------------
# The start-up flow, on a pretend machine
# ---------------------------------------------------------------------------


class _Clock:
    """A clock the wait loop can run on without waiting: sleeping advances it."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _Machine:
    """Which fpstune instances run, what else listens, and who holds the lock port.

    The instance lock is held while any fpstune instance runs or
    ``stray_lock_holder`` is set; a stop request (when ``stoppable``) ends the
    instance and so releases it. ``lock_frees_at`` frees it at a fake time.
    """

    def __init__(
        self,
        fpstune: set[int],
        others: dict[int, object] | None = None,
        *,
        stoppable: bool = True,
        stray_lock_holder: bool = False,
        lock_frees_at: float | None = None,
    ) -> None:
        self.fpstune = set(fpstune)
        self.others = others or {}
        self.stoppable = stoppable
        self.stray_lock_holder = stray_lock_holder
        self.lock_frees_at = lock_frees_at
        self.clock = _Clock()
        self.probed: list[int] = []
        self.posted: list[int] = []
        self.lock = object()

    def fetch_health(self, port: int) -> object | None:
        self.probed.append(port)
        if port in self.fpstune:
            return _fpstune_health()
        return self.others.get(port)

    def post_stop(self, port: int) -> int | None:
        self.posted.append(port)
        if port not in self.fpstune:
            return None
        if not self.stoppable:
            return 404
        self.fpstune.discard(port)
        return 202

    def acquire_lock(self) -> object | None:
        if self.lock_frees_at is not None and self.clock.now >= self.lock_frees_at:
            return self.lock
        if self.fpstune or self.stray_lock_holder:
            return None
        return self.lock


@pytest.fixture
def machine_with(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[..., _Machine]:
    """Build a pretend machine and route the CLI's probes, stop requests, lock and clock to it."""

    def build(pid_file_port: int | None = None, fpstune: set[int] | None = None, **kwargs: object):
        machine = _Machine(fpstune or set(), **kwargs)  # type: ignore[arg-type]
        pid_file = tmp_path / "fpstune_serve.pid"
        if pid_file_port is not None:
            pid_file.write_text(json.dumps({"pid": 4242, "port": pid_file_port}), encoding="utf-8")
        monkeypatch.setattr(cli, "_get_pid_file", lambda: str(pid_file))
        monkeypatch.setattr(cli.instances, "fetch_health", machine.fetch_health)
        monkeypatch.setattr(cli.instances, "post_stop", machine.post_stop)
        monkeypatch.setattr(cli, "_acquire_instance_lock", machine.acquire_lock)
        monkeypatch.setattr(cli, "time", machine.clock)
        monkeypatch.setattr(cli, "_lock_sock", None)
        return machine

    return build


class TestANewStartClosesTheRunningOne:
    def test_a_free_lock_means_nothing_is_probed_or_stopped(self, machine_with) -> None:
        machine = machine_with()

        cli._claim_single_instance(preferred_port=8000)

        assert cli._lock_sock is machine.lock
        assert machine.probed == [] and machine.posted == []

    def test_one_running_instance_is_asked_to_stop_and_the_start_goes_on(
        self, machine_with, capsys
    ) -> None:
        machine = machine_with(fpstune={8000})

        cli._claim_single_instance(preferred_port=8000)

        assert machine.posted == [8000]
        assert cli._lock_sock is machine.lock
        assert "already running" in capsys.readouterr().out

    def test_two_instances_on_different_ports_are_both_stopped(self, machine_with) -> None:
        """An instance a crashed earlier start left on another port is found by
        the range scan; stopping only the first would leave it serving."""
        machine = machine_with(fpstune={8000, 8003})

        cli._claim_single_instance(preferred_port=8000)

        assert sorted(machine.posted) == [8000, 8003]
        assert machine.fpstune == set()
        assert cli._lock_sock is machine.lock

    def test_the_pid_files_port_is_found_even_outside_the_scanned_range(self, machine_with) -> None:
        machine = machine_with(pid_file_port=9123, fpstune={9123})

        cli._claim_single_instance(preferred_port=8000)

        assert machine.posted == [9123]
        assert machine.probed[0] == 9123, "the PID file's port is the first lead"

    def test_the_whole_range_serve_picks_from_is_scanned_and_nothing_beyond(
        self, machine_with
    ) -> None:
        machine = machine_with(fpstune={8000})

        cli._claim_single_instance(preferred_port=8000)

        assert sorted(machine.probed) == list(range(8000, 8000 + instances.SCAN_ATTEMPTS))

    def test_a_non_fpstune_server_on_a_scanned_port_is_left_alone(self, machine_with) -> None:
        """Never act on a guess: a stranger's /health, including one that copies
        the single key the old check looked for, is not fpstune."""
        machine = machine_with(
            fpstune={8000},
            others={
                8001: {"status": "ok"},
                8002: {"status": "healthy", "subsystems": {}},
                8003: ["not", "an", "object"],
                8004: "plain text",
            },
        )

        cli._claim_single_instance(preferred_port=8000)

        assert machine.posted == [8000]

    def test_an_instance_that_is_still_starting_is_waited_for(self, machine_with) -> None:
        """The lock is held by a start with no API up yet: nothing to ask, so the
        start waits (bounded) and takes the lock when it frees."""
        machine = machine_with(stray_lock_holder=True, lock_frees_at=3.0)

        cli._claim_single_instance(preferred_port=8000)

        assert machine.posted == []
        assert cli._lock_sock is machine.lock
        assert 3.0 <= machine.clock.now < cli._TAKEOVER_WAIT_SECONDS


class TestTheTakeoverGivesUpClearly:
    def test_an_instance_that_refuses_the_stop_ends_in_a_named_failure(
        self, machine_with, capsys
    ) -> None:
        """An older fpstune has no stop request (404): the start fails after the
        bounded wait and says what was tried, instead of hanging or guessing."""
        machine = machine_with(pid_file_port=8123, fpstune={8123, 8001}, stoppable=False)

        with pytest.raises(SystemExit) as exited:
            cli._claim_single_instance(preferred_port=8000)

        out = capsys.readouterr().out
        assert exited.value.code == 1
        assert cli._lock_sock is None
        assert sorted(machine.posted) == [8001, 8123]
        assert "still holds the instance lock" in out
        assert "8123" in out and "8001" in out and "HTTP 404" in out
        assert cli._TAKEOVER_WAIT_SECONDS <= machine.clock.now < cli._TAKEOVER_WAIT_SECONDS + 1

    def test_a_lock_held_by_something_that_is_not_fpstune_says_nothing_was_asked(
        self, machine_with, capsys
    ) -> None:
        machine = machine_with(stray_lock_holder=True, others={8000: {"status": "ok"}})

        with pytest.raises(SystemExit) as exited:
            cli._claim_single_instance(preferred_port=8000)

        out = capsys.readouterr().out
        assert exited.value.code == 1
        assert machine.posted == []
        assert "nothing was asked to stop" in out
        assert str(cli._LOCK_PORT) in out


class TestWaitForLock:
    def test_it_reports_progress_while_it_waits(self, capsys) -> None:
        clock = _Clock()
        with patch.object(cli, "_acquire_instance_lock", return_value=None):
            result = cli._wait_for_lock(12.0, sleep=clock.sleep, clock=clock.monotonic)

        out = capsys.readouterr().out
        assert result is None
        assert "Still waiting (5 s)" in out and "Still waiting (10 s)" in out
        assert "Still waiting (15 s)" not in out

    def test_it_returns_the_lock_the_moment_the_port_frees(self) -> None:
        clock = _Clock()
        lock = object()
        answers = iter([None, None, lock])
        with patch.object(cli, "_acquire_instance_lock", side_effect=lambda: next(answers)):
            result = cli._wait_for_lock(20.0, sleep=clock.sleep, clock=clock.monotonic)

        assert result is lock
        assert clock.now == 2 * cli._TAKEOVER_POLL_SECONDS


class TestServeClaimsBeforeItWritesAnything:
    def test_the_requested_port_is_where_the_scan_starts(self) -> None:
        with (
            patch.object(cli.ui, "print_banner"),
            patch.object(cli, "_claim_single_instance") as claim,
            patch.object(cli, "_find_free_port", return_value=8123),
            patch.object(cli, "_write_pid_file"),
            patch.object(cli, "_ensure_administrator", return_value=False),
        ):
            CliRunner().invoke(cli.serve, ["--port", "8123"])

        claim.assert_called_once_with(preferred_port=8123)


class TestTheNewerInstanceKeepsItsPidFile:
    def test_the_old_one_removes_its_pid_file_before_freeing_the_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Freeing the lock lets the newer start in at once and write its own PID
        file; one removed after that would be the newer instance's."""
        pid_file = tmp_path / "fpstune_serve.pid"
        pid_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(cli, "_get_pid_file", lambda: str(pid_file))
        seen: list[bool] = []

        class _Lock:
            def close(self) -> None:
                seen.append(pid_file.exists())

        monkeypatch.setattr(cli, "_lock_sock", _Lock())

        cli._shutdown_cleanup()

        assert seen == [False], "the lock was freed while the PID file was still there"
        assert cli._lock_sock is None
