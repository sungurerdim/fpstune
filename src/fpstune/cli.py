"""Command-line interface for fpstune."""

from __future__ import annotations

import contextlib
import logging
import socket
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import click

from fpstune import __version__
from fpstune.commands import (
    benchmark,
    cleanup,
    dpc_bench,
    fps,
    gpu,
    gpu_bench,
    network_bench,
    nvidia_dump,
    status,
)
from fpstune.commands import presentation as ui
from fpstune.commands.utils import console, require_admin_or_elevate
from fpstune.utils.admin import elevate_if_needed, is_admin
from fpstune.utils.logger import setup_logging
from fpstune.utils.runtime import frontend_dist, frontend_source, is_frozen

if TYPE_CHECKING:
    import subprocess
    import types

# ---------------------------------------------------------------------------
# Re-export names that external code (including tests) patches on fpstune.cli
# ---------------------------------------------------------------------------
from fpstune.utils.detect import get_gpu_info as get_gpu_info  # noqa: F401
from fpstune.utils.detect import get_os_info as get_os_info  # noqa: F401
from fpstune.utils.system_tools import pin_powershell_module_cache, system_tool

_LOCK_PORT = 59471  # Fixed internal port used as single-instance mutex

# Held for the lifetime of `serve`. Module-level because the packaged path hands
# control to uvicorn and the source path to a signal handler, and both have to
# be able to release it — a local would have been closed by whichever returned
# first, freeing the lock while fpstune was still running.
_lock_sock: socket.socket | None = None


def _get_pid_file() -> str:
    import os
    import tempfile

    return os.path.join(tempfile.gettempdir(), "fpstune_serve.pid")


def _acquire_instance_lock() -> socket.socket | None:
    """Bind a local socket to serve as a single-instance lock.

    Returns the bound socket (caller must keep it alive) or None if another
    instance is already running.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", _LOCK_PORT))
        return sock
    except OSError:
        sock.close()
        return None


def _write_pid_file(pid: int, port: int) -> None:
    import json

    try:
        with open(_get_pid_file(), "w", encoding="utf-8") as f:
            json.dump({"pid": pid, "port": port}, f)
    except OSError:
        pass


def _remove_pid_file() -> None:
    import contextlib
    import os

    with contextlib.suppress(OSError):
        os.unlink(_get_pid_file())


def _running_instance_url() -> str | None:
    """The UI of the fpstune already running here, if one answers.

    The PID file names the port it serves on; asking that port's /health is the
    whole check. A stale file, a reused port or another program on it simply
    does not answer as fpstune, so nothing is ever killed on a guess.
    """
    import json
    import urllib.request

    try:
        with open(_get_pid_file(), encoding="utf-8") as f:
            port = int(json.load(f)["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    url = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=2) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict) or "subsystems" not in body:
        return None
    return f"{url}/ui"


def _find_free_port(preferred: int, max_attempts: int = 10) -> int:
    """The first TCP port from ``preferred`` this process can bind."""
    for port in range(preferred, preferred + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise click.ClickException(
        f"Ports {preferred}-{preferred + max_attempts - 1} are all in use. "
        f"Close the program holding them, or start with --port <number>."
    )


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="fpstune")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """fpstune - Windows Gaming Performance Optimizer

    Optimize your Windows system for gaming with safe, reversible tweaks.

    \b
    Run without arguments to start the Web UI:
        fpstune

    \b
    Or use subcommands:
        fpstune status    What this machine is set to, and what is left to do
        fpstune gpu       How this GPU is configured
        fpstune nvidia-dump  Save NVIDIA driver settings to a file, for diagnosis
        fpstune benchmark Measure this machine, before and after
        fpstune cleanup   Free disk space
        fpstune serve     Start the web UI (same as no args)

    \b
    Applying is done from the web UI, which is the only path that verifies
    each change actually took effect.
    """
    pin_powershell_module_cache()

    # Require admin privileges - shows UAC prompt on Windows if needed
    require_admin_or_elevate()

    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # `serve` is a server and its log *is* the output, so INFO belongs there.
    # Every other command prints a report, and an INFO line from the detector
    # arriving mid-report reads as part of the report:
    #
    #     Elevated  no - some settings cannot be read
    #     INFO | detect | GPU detection: Trying nvidia-smi...
    #     Where this machine stands
    #
    # Anything a report command genuinely needs to say, it says itself. `-v`
    # still turns everything back on.
    if verbose:
        level = logging.DEBUG
    elif ctx.invoked_subcommand in (None, "serve"):
        level = logging.INFO
    else:
        level = logging.WARNING
    setup_logging(level=level)

    # If no subcommand, start the web UI
    if ctx.invoked_subcommand is None:
        ctx.invoke(serve)


# ---------------------------------------------------------------------------
# Register command modules
# ---------------------------------------------------------------------------
main.add_command(benchmark)
main.add_command(cleanup)
main.add_command(dpc_bench)
main.add_command(fps)
main.add_command(gpu)
main.add_command(gpu_bench)
main.add_command(network_bench)
main.add_command(nvidia_dump)
main.add_command(status)


# ---------------------------------------------------------------------------
# bios command (kept here - small standalone utility)
# ---------------------------------------------------------------------------


@main.command()
@click.option("--delay", "-d", default=10, help="Delay in seconds before reboot")
@click.option("--cancel", "-c", is_flag=True, help="Cancel a scheduled BIOS reboot")
def bios(delay: int, cancel: bool) -> None:
    """Reboot directly to BIOS/UEFI firmware settings.

    Useful for changing boot order, enabling XMP, or other BIOS settings.

    \b
    Examples:
        fpstune bios           # Reboot to BIOS in 10 seconds
        fpstune bios -d 30     # Reboot to BIOS in 30 seconds
        fpstune bios --cancel  # Cancel scheduled reboot
    """
    import subprocess as sp

    if cancel:
        result = sp.run([system_tool("shutdown.exe"), "/a"], capture_output=True, text=True)
        if result.returncode == 0:
            console.print("[green]\u2713[/] Scheduled reboot cancelled")
        else:
            console.print("[yellow]![/] No scheduled reboot to cancel")
        return

    console.print(f"[bold yellow]System will reboot to BIOS in {delay} seconds![/]")
    console.print("[dim]Run 'fpstune bios --cancel' to abort[/]\n")

    result = sp.run(
        [system_tool("shutdown.exe"), "/r", "/fw", "/t", str(delay)],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        console.print(
            f"[green]\u2713[/] Reboot scheduled. Entering BIOS/UEFI in {delay} seconds..."
        )
        console.print("\n[dim]Save your work! Press Ctrl+C won't stop the reboot.[/]")
        console.print("[dim]Use 'fpstune bios --cancel' or 'shutdown /a' to abort.[/]")
    else:
        console.print(f"[red]\u2717[/] Failed to schedule reboot: {result.stderr}")


# ---------------------------------------------------------------------------
# serve command (Web UI)
# ---------------------------------------------------------------------------


@main.command()
@click.option("--port", "-p", default=8000, help="API server port")
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
@click.option("--dev", is_flag=True, help="Source only: Vite dev server with live reload")
@click.option("--ui-port", default=5173, help="Vite dev server port (with --dev)")
@click.option("--api-only", is_flag=True, help="With --dev: start the API without Vite")
def serve(port: int, no_browser: bool, dev: bool, ui_port: int, api_only: bool) -> None:
    """Start the fpstune web UI.

    The API runs in this process and serves the built UI, from the executable
    or, in a source checkout, from frontend/dist (built first if it is missing
    or older than its source). --dev runs Vite with live reload instead.

    \b
    Examples:
        fpstune serve              # start, open the browser
        fpstune serve --no-browser # don't open the browser
        fpstune serve --dev        # source checkout: Vite with live reload
    """
    import os

    ui.print_banner()

    if not _claim_single_instance(open_browser=not no_browser):
        return

    port = _find_free_port(port)
    _write_pid_file(os.getpid(), port)

    if not _ensure_administrator():
        return

    if dev and not is_frozen():
        _serve_from_source(port=port, ui_port=ui_port, no_browser=no_browser, api_only=api_only)
        return
    if not is_frozen() and not _ensure_built_ui():
        raise SystemExit(1)
    _serve_in_process(port=port, no_browser=no_browser)


def _claim_single_instance(*, open_browser: bool) -> bool:
    """Take the single-instance lock, or hand the user to the instance that has it.

    A second start never kills the first: it opens the running instance's UI and
    stops. That is what a user starting fpstune again wants, and it needs no
    process inspection — the previous version matched netstat's English
    "LISTENING", which a Turkish or German Windows never prints.
    """
    global _lock_sock
    _lock_sock = _acquire_instance_lock()
    if _lock_sock is not None:
        return True

    url = _running_instance_url()
    if url is not None:
        ui.ok("fpstune is already running", url)
        if open_browser:
            import webbrowser

            webbrowser.open(url)
        return False

    ui.fail("Another fpstune is starting or shutting down")
    ui.hint(["Wait a few seconds and start it again"])
    raise SystemExit(1)


def _ensure_built_ui() -> bool:
    """Build frontend/dist when it is missing or older than its source.

    Node comes with the dev extra (`uv sync --extra dev` installs the
    nodejs-wheel package), so a checkout needs nothing but uv; a system-wide
    Node.js works as well.
    """
    import shutil
    import subprocess

    source = frontend_source()
    if source is None:
        return frontend_dist() is not None

    dist_index = source / "dist" / "index.html"
    watched = [source / "index.html", source / "package-lock.json", source / "vite.config.ts"]
    newest = max(
        [p.stat().st_mtime for p in watched if p.exists()]
        + [p.stat().st_mtime for p in (source / "src").rglob("*") if p.is_file()],
        default=0.0,
    )
    if dist_index.exists() and dist_index.stat().st_mtime >= newest:
        return True

    npm = shutil.which("npm")
    if npm is None:
        ui.fail("The UI needs building once, and npm was not found")
        ui.hint(
            [
                "Run: uv sync --extra dev   (installs Node.js into this project's environment)",
                "Then start fpstune again with: uv run fpstune serve",
            ]
        )
        return False

    steps = [] if (source / "node_modules").is_dir() else [[npm, "ci"]]
    steps.append([npm, "run", "build"])
    for argv in steps:
        ui.step(f"Building the UI: {' '.join(argv[1:])}")
        result = subprocess.run(argv, cwd=source, check=False)
        if result.returncode != 0:
            ui.fail(f"'{' '.join(argv[1:])}' failed", f"exit code {result.returncode}")
            return False
    return dist_index.exists()


def _ensure_administrator() -> bool:
    """True when elevated. Otherwise ask for elevation and tell the caller to stop.

    fpstune writes HKLM values, service start types and power schemes. Carrying
    on without them means every write fails with access denied, which reads to a
    user as "it did nothing" — so this refuses rather than degrades.
    """
    if is_admin():
        ui.ok("Running as Administrator")
        return True

    ui.warn(
        "Administrator is required",
        "the registry, services and power schemes are not writable otherwise",
    )
    ui.step("Requesting elevation")

    if elevate_if_needed():
        ui.ok("Elevation requested", "this window closes and an elevated one opens")
        return False

    ui.fail("Elevation was declined or unavailable")
    ui.hint(
        [
            "Right-click Command Prompt or PowerShell",
            "Choose 'Run as administrator'",
            "Run: fpstune serve",
        ]
    )
    raise SystemExit(1)


def _serve_in_process(*, port: int, no_browser: bool) -> None:
    """Run the API in this process and serve the built UI.

    Deliberately spawns nothing. ``sys.executable`` in a frozen build is
    ``fpstune.exe``, so the old ``[sys.executable, "-m", "uvicorn", ...]``
    relaunched fpstune with arguments its own CLI rejects: the child exited
    immediately and the parent reported "API process exited" once a second for
    as long as the window stayed open.
    """
    import threading
    import webbrowser

    import uvicorn

    from fpstune.api.main import app

    url = f"http://127.0.0.1:{port}"

    if frontend_dist() is None:
        # The packaging spec refuses to build without it, so reaching this means
        # someone built around the spec. Say which, rather than "not found".
        ui.warn("This build carries no UI", "only the API and its docs are available")
        landing = f"{url}/docs"
    else:
        landing = f"{url}/ui"

    ui.blank()
    ui.details(
        [("Web UI", landing), ("API", url), ("Docs", f"{url}/docs")],
        title="fpstune is running",
    )
    ui.blank()
    ui.info("Press Ctrl+C to stop")
    ui.blank()

    if not no_browser:
        # After the server is listening, not before: opening first shows the
        # browser its own error page and the user reloads by hand.
        threading.Timer(1.0, lambda: webbrowser.open(landing)).start()

    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown_cleanup()
        ui.blank()
        ui.ok("Goodbye")


def _pump_output(name: str, proc: subprocess.Popen[bytes]) -> None:
    """Relay a child's output line by line until it closes its pipe.

    The children used to write into pipes nobody read: their logs were invisible,
    and once a pipe's buffer filled (64 KB of uvicorn output — an hour of use) the
    child blocked on its next write and the API stopped answering. Reading here
    is what keeps the child alive; the relay is what makes the logs visible.
    """
    stdout = getattr(proc, "stdout", None)
    if stdout is None:
        return
    for raw in stdout:
        ui.relay(name, raw.decode("utf-8", errors="replace").rstrip("\r\n"))


class _GroupOptions(TypedDict, total=False):
    creationflags: int
    start_new_session: bool


def _own_process_group() -> _GroupOptions:
    """Popen options that give a dev-server child a process group of its own.

    The shutdown stops each child on its own: ``terminate`` on Windows, a
    ``killpg`` of the child's group elsewhere. Off Windows a child started
    without a session of its own shares fpstune's group, so that signal would
    land on fpstune and on the terminal job it was started from.
    """
    import subprocess

    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _serve_from_source(*, port: int, ui_port: int, no_browser: bool, api_only: bool) -> None:
    """Run the API and the Vite dev server as children, so both reload on edit."""
    import os
    import signal
    import subprocess
    import threading
    import time
    import webbrowser

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    frontend_dir = frontend_source()

    # The children cannot see the terminal, so left alone they print plain text.
    # FORCE_COLOR asks their loggers (Rich honours it, so does Vite) to colour
    # anyway; `relay` parses those escapes and this console renders them by
    # whatever means it has. Only asked for when there is a terminal to render.
    # FPSTUNE_API_PORT points Vite's /api proxy at the port actually chosen; it
    # was fixed at 8000, so a fallback port left the dev UI talking to nothing.
    child_env = {**os.environ, "FPSTUNE_API_PORT": str(port)}
    if ui.console.is_terminal:
        child_env["FORCE_COLOR"] = "1"

    if not api_only and frontend_dir is None:
        ui.warn("No frontend source tree here", "serving the API alone")
        api_only = True

    ui.step(f"Starting the API on port {port}")
    try:
        api_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "fpstune.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=child_env,
            **_own_process_group(),
        )
        processes.append(("API", api_process))
        threading.Thread(target=_pump_output, args=("API", api_process), daemon=True).start()
        ui.ok("API started", f"http://127.0.0.1:{port}")
    except OSError as e:
        ui.fail("Could not start the API", str(e))
        return

    import shutil

    npm = shutil.which("npm")
    if not api_only and frontend_dir is not None and npm is None:
        ui.warn("npm not found", "run 'uv sync --extra dev'; serving the API alone")
        api_only = True

    if not api_only and frontend_dir is not None and npm is not None:
        if not (frontend_dir / "node_modules").exists():
            ui.step("Installing frontend dependencies", "first run only")
            install = subprocess.run(
                [npm, "ci"],
                cwd=frontend_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if install.returncode != 0:
                ui.warn("npm ci failed", "continuing; the dev server may not start")

        ui.step(f"Starting the frontend on port {ui_port}")
        try:
            frontend_process = subprocess.Popen(
                [npm, "run", "dev", "--", "--port", str(ui_port)],
                cwd=frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=child_env,
                **_own_process_group(),
            )
            processes.append(("Frontend", frontend_process))
            threading.Thread(
                target=_pump_output, args=("WEB", frontend_process), daemon=True
            ).start()
            ui.ok("Frontend started", f"http://localhost:{ui_port}")
        except OSError as e:
            ui.warn("Could not start the frontend", str(e))
            api_only = True

    time.sleep(2)

    landing = f"http://127.0.0.1:{port}/docs" if api_only else f"http://localhost:{ui_port}"

    ui.blank()
    rows = [] if api_only else [("Web UI", landing)]
    rows += [("API", f"http://127.0.0.1:{port}"), ("Docs", f"http://127.0.0.1:{port}/docs")]
    ui.details(rows, title="fpstune is running")
    ui.blank()
    ui.info("Press Ctrl+C to stop")
    ui.blank()

    if not no_browser:
        webbrowser.open(landing)

    def shutdown(_signum: int | None = None, _frame: types.FrameType | None = None) -> None:
        import os

        ui.blank()
        ui.step("Shutting down")
        for name, proc in processes:
            try:
                if sys.platform == "win32":
                    proc.terminate()
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                ui.info(f"Stopped {name}")
            except (OSError, ProcessLookupError):
                pass
        _shutdown_cleanup()
        ui.ok("Goodbye")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            for name, proc in processes:
                if proc.poll() is not None:
                    # Reported once and then we stop. The old loop printed this
                    # every second for as long as the window stayed open, which
                    # is how a dead child looked like a working app.
                    ui.fail(f"{name} exited unexpectedly")
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


def _shutdown_cleanup() -> None:
    """Release the single-instance lock and the PID file. Safe to call twice."""
    import contextlib

    global _lock_sock
    if _lock_sock is not None:
        with contextlib.suppress(OSError):
            _lock_sock.close()
        _lock_sock = None
    _remove_pid_file()


@main.command(name="update")
def update_command() -> None:
    """Check whether a newer fpstune has been released.

    Asks only when you run it. fpstune sends nothing about you or your machine —
    the request is a plain GET of a fixed public URL — and nothing else in the
    tool reaches the network unless you ask it to.
    """
    from fpstune.utils.updates import check_for_update

    ui.blank()
    ui.step("Checking for a newer release")
    result = check_for_update()

    if not result.reachable:
        # Not an error worth a non-zero exit: nothing the user did is wrong, and
        # the answer is simply unknown rather than "you are up to date".
        ui.warn("Could not check", result.error or "unknown reason")
        ui.info("Releases", result.url)
        ui.blank()
        return

    if result.update_available:
        ui.ok(f"fpstune {result.latest} is available", f"you have {result.current}")
        ui.blank()
        ui.link("Download", result.url)
    else:
        ui.ok(f"fpstune {result.current} is the latest release")
    ui.blank()


def run() -> None:
    """Entry point: the CLI, with a crash report instead of a vanishing window.

    The packaged exe opens its own console, which closes the moment the process
    ends — so an unhandled error used to leave nothing at all to report. The
    traceback now goes to a file, its path is printed, and the window waits.
    """
    if is_frozen():
        from fpstune.utils.updates import remove_replaced_executable

        remove_replaced_executable()
    try:
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception:
        path = _write_crash_report()
        ui.blank()
        ui.fail("fpstune stopped because of an unexpected error")
        if path is not None:
            ui.info("Details were saved to", str(path))
            ui.info("Please attach that file when reporting the problem")
        if is_frozen() and sys.stdin is not None and sys.stdin.isatty():
            with contextlib.suppress(EOFError, KeyboardInterrupt):
                input("Press Enter to close this window...")
        raise SystemExit(1) from None


def _write_crash_report() -> Path | None:
    """Traceback, version and platform — nothing about the user — to a file."""
    import platform
    import traceback
    from datetime import datetime

    from fpstune.utils.config import get_config_dir

    try:
        folder = get_config_dir() / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"crash-{datetime.now():%Y%m%d-%H%M%S}.txt"
        path.write_text(
            f"fpstune {__version__}\n"
            f"{platform.platform()} | Python {platform.python_version()} | "
            f"frozen={is_frozen()}\n\n{traceback.format_exc()}",
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


if __name__ == "__main__":
    run()
