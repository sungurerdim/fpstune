"""A packaged build is not a source checkout, and `serve` used to assume it was.

Both failures below were reported from a real run of the built executable, and
neither had a test — the suite only ever ran from a source tree, where both
assumptions happen to hold.

    Warning: Frontend not found at C:\\Users\\<name>\\AppData\\Local\\frontend
    ...
    Warning: API process exited
    Warning: API process exited
    Warning: API process exited

**Paths.** `Path(__file__).parent.parent.parent / "frontend"` climbs three
levels from wherever the module lives. From a source tree that is the repo root.
From inside a PyInstaller executable, `__file__` is in a temporary extraction
directory, so it lands somewhere fpstune has never written anything — and it was
looking for the *dev* frontend, with a package.json and node_modules, which a
packaged build has no use for anyway.

**Re-execution.** `sys.executable` is the Python interpreter from source and is
`fpstune.exe` when frozen. `serve` spawned `[sys.executable, "-m", "uvicorn",
...]`, so the packaged build relaunched itself with arguments its own CLI
rejects. The child died immediately, and the watchdog printed "API process
exited" once a second for as long as the window stayed open — forever, because
nothing in that loop ever stopped.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from fpstune import cli
from fpstune.utils import runtime


@pytest.fixture
def frozen(tmp_path: Path):
    """Make the process look like a PyInstaller build with a bundled UI."""
    bundle = tmp_path / "_MEI123"
    (bundle / "frontend" / "dist").mkdir(parents=True)
    (bundle / "frontend" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "_MEIPASS", str(bundle), create=True),
        # The give-away: in a frozen build this is the executable, not Python.
        patch.object(sys, "executable", str(tmp_path / "fpstune.exe")),
    ):
        yield bundle


class TestRuntimeKnowsWhereItIs:
    def test_a_source_checkout_is_not_frozen(self) -> None:
        assert runtime.is_frozen() is False

    @pytest.mark.usefixtures("frozen")
    def test_a_frozen_build_is_detected(self) -> None:
        assert runtime.is_frozen() is True

    def test_the_bundled_ui_is_found_inside_the_bundle(self, frozen: Path) -> None:
        """Not three levels up from a temp directory."""
        assert runtime.frontend_dist() == frozen / "frontend" / "dist"

    @pytest.mark.usefixtures("frozen")
    def test_a_frozen_build_reports_no_frontend_source(self) -> None:
        """There is no package.json to run Vite from, and asking for one is how
        the "frontend not found" path was reached."""
        assert runtime.frontend_source() is None

    def test_a_source_checkout_finds_its_own_frontend(self) -> None:
        source = runtime.frontend_source()
        assert source is not None
        assert (source / "package.json").is_file()


class TestPackagedServeSpawnsNothing:
    """The whole class of bug: a frozen build must not re-execute itself."""

    @pytest.mark.usefixtures("frozen")
    def test_it_starts_no_subprocess(self) -> None:
        served: dict[str, object] = {}

        def fake_run(_app, **kwargs):
            served.update(kwargs)

        with (
            patch.object(
                subprocess, "Popen", side_effect=AssertionError("packaged serve spawned a process")
            ),
            patch("uvicorn.run", fake_run),
        ):
            cli._serve_packaged(port=8123, no_browser=True)

        assert served["port"] == 8123
        assert served["host"] == "127.0.0.1"

    @pytest.mark.usefixtures("frozen")
    def test_it_serves_the_bundled_ui(self, capsys) -> None:
        with patch("uvicorn.run"):
            cli._serve_packaged(port=8123, no_browser=True)

        printed = capsys.readouterr().out
        assert "/ui" in printed, "the packaged build must point at the UI it carries"
        assert "AppData" not in printed

    def test_it_says_so_when_the_build_carries_no_ui(self, tmp_path: Path, capsys) -> None:
        """Reaching this means someone built around the spec, which refuses it.

        Naming that is more use than repeating "frontend not found" at a path
        the user has never heard of.
        """
        empty = tmp_path / "_MEI_empty"
        empty.mkdir()
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "_MEIPASS", str(empty), create=True),
            patch.object(runtime, "_SOURCE_ROOT", empty),
            patch("uvicorn.run"),
        ):
            cli._serve_packaged(port=8123, no_browser=True)

        printed = capsys.readouterr().out
        assert "carries no UI" in printed
        assert "/docs" in printed

    @pytest.mark.usefixtures("frozen")
    def test_it_releases_the_instance_lock_when_the_server_stops(self) -> None:
        """uvicorn.run blocks until shutdown, so the release has to be in a
        finally — a packaged build never reaches the source path's signal
        handler."""
        cli._lock_sock = None
        with patch("uvicorn.run", side_effect=KeyboardInterrupt):
            cli._serve_packaged(port=8123, no_browser=True)
        assert cli._lock_sock is None


class TestTheSourcePathStillSpawns:
    """Fixing the packaged path must not take the dev workflow with it."""

    def test_it_starts_the_api_as_a_child(self) -> None:
        started: list[list[str]] = []

        class _Alive:
            def __init__(self, argv, **_kwargs):
                started.append(argv)

            def poll(self):
                return None

            def terminate(self):
                return None

        # The first sleep is the two-second settle before the summary; only the
        # one inside the watchdog loop should end the test, or this never gets
        # as far as the loop it is about.
        sleeps = iter([None, KeyboardInterrupt()])

        def fake_sleep(_seconds: float) -> None:
            outcome = next(sleeps, KeyboardInterrupt())
            if isinstance(outcome, BaseException):
                raise outcome

        with (
            patch.object(subprocess, "Popen", _Alive),
            patch("time.sleep", fake_sleep),
            patch.object(cli, "_shutdown_cleanup"),
            pytest.raises(SystemExit),
        ):
            cli._serve_from_source(port=8123, ui_port=5199, no_browser=True, api_only=True)

        assert started, "the source path stopped starting the API"
        assert "uvicorn" in started[0]


class TestADeadChildIsReportedOnce:
    def test_it_stops_instead_of_repeating_the_warning(self, capsys) -> None:
        """The original loop printed "API process exited" every second forever.

        A watchdog that notices a dead child and then does nothing about it is
        how a broken run looked like a working one.
        """

        class _Dead:
            def __init__(self, *_a, **_k):
                pass

            def poll(self):
                return 1

            def terminate(self):
                return None

        with (
            patch.object(subprocess, "Popen", _Dead),
            patch("time.sleep"),
            patch.object(cli, "_shutdown_cleanup"),
            pytest.raises(SystemExit),
        ):
            cli._serve_from_source(port=8123, ui_port=5199, no_browser=True, api_only=True)

        printed = capsys.readouterr().out
        assert printed.count("exited unexpectedly") == 1, (
            "the dead child was reported more than once; the watchdog is looping again"
        )
