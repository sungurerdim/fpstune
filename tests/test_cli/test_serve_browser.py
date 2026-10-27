"""The browser hand-off after `fpstune serve` (P-POLA: it must actually open).

Two failures shipped as "the UI never opened": a fixed one-second delay that
opened the browser before uvicorn had bound (the user got the browser's own
error page), and an elevated process being refused the shell hand-off that
`webbrowser` uses. The helper polls the port and falls back to `explorer.exe`,
which opens the URL with the logged-in user's shell.
"""

from __future__ import annotations

import socket
import time

import pytest

from fpstune import cli
from fpstune.utils.system_tools import explorer_exe


@pytest.fixture
def listening_port() -> int:
    """A port something is listening on, closed when the test ends."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        yield server.getsockname()[1]
    finally:
        server.close()


@pytest.fixture
def closed_port() -> int:
    """A port nothing listens on (bound and released, so it is a real free port)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class TestTheBrowserOpens:
    def test_it_opens_the_landing_page_once_the_port_answers(
        self, listening_port: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opened: list[str] = []

        def fake_open(url: str) -> bool:
            opened.append(url)
            return True

        monkeypatch.setattr("webbrowser.open", fake_open)
        landing = f"http://127.0.0.1:{listening_port}/ui"
        cli._open_web_ui_when_ready(landing, listening_port, timeout=3.0)
        assert opened == [landing]

    def test_a_refused_hand_off_falls_back_to_explorer(
        self, listening_port: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("webbrowser.open", lambda _url: False)
        launched: list[list[str]] = []

        def fake_popen(argv: list[str], **_kwargs: object) -> object:
            launched.append(argv)
            return object()

        monkeypatch.setattr("subprocess.Popen", fake_popen)
        landing = f"http://127.0.0.1:{listening_port}/ui"
        cli._open_web_ui_when_ready(landing, listening_port, timeout=3.0)
        assert launched == [[explorer_exe(), landing]]

    def test_a_browser_error_falls_back_to_explorer(
        self, listening_port: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import webbrowser

        def raising_open(_url: str) -> bool:
            raise webbrowser.Error("no usable browser")

        monkeypatch.setattr("webbrowser.open", raising_open)
        launched: list[list[str]] = []
        monkeypatch.setattr(
            "subprocess.Popen",
            lambda argv, **_kwargs: launched.append(argv) or object(),
        )
        landing = f"http://127.0.0.1:{listening_port}/ui"
        cli._open_web_ui_when_ready(landing, listening_port, timeout=3.0)
        assert launched == [[explorer_exe(), landing]]

    def test_a_closed_port_does_not_wait_forever(
        self, closed_port: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opened: list[str] = []
        monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
        started = time.monotonic()
        cli._open_web_ui_when_ready("http://127.0.0.1:1/ui", closed_port, timeout=0.4)
        assert time.monotonic() - started < 5.0
        # It still tries once: a slow server must not leave the user with no tab.
        assert opened == ["http://127.0.0.1:1/ui"]

    def test_a_missing_explorer_is_logged_not_raised(
        self,
        listening_port: int,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setattr("webbrowser.open", lambda _url: False)

        def no_explorer(_argv: list[str], **_kwargs: object) -> object:
            raise OSError("explorer.exe not found")

        monkeypatch.setattr("subprocess.Popen", no_explorer)
        landing = f"http://127.0.0.1:{listening_port}/ui"
        with caplog.at_level("WARNING", logger="fpstune.cli"):
            cli._open_web_ui_when_ready(landing, listening_port, timeout=3.0)
        assert "Could not open a browser" in caplog.text
        assert landing in caplog.text

    def test_an_unresolvable_windows_directory_starts_nothing(
        self,
        listening_port: int,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setattr("webbrowser.open", lambda _url: False)
        monkeypatch.setattr(cli, "explorer_exe", lambda: None)
        launched: list[list[str]] = []
        monkeypatch.setattr(
            "subprocess.Popen",
            lambda argv, **_kwargs: launched.append(argv) or object(),
        )
        landing = f"http://127.0.0.1:{listening_port}/ui"
        with caplog.at_level("WARNING", logger="fpstune.cli"):
            cli._open_web_ui_when_ready(landing, listening_port, timeout=3.0)
        assert launched == []
        assert "Could not open a browser" in caplog.text
