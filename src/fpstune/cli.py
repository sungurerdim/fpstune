"""Command-line interface for fpstune."""

from __future__ import annotations

import logging
import socket
import sys
from typing import TYPE_CHECKING

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
    status,
)
from fpstune.commands import presentation as ui
from fpstune.commands.utils import console, require_admin_or_elevate
from fpstune.utils.admin import elevate_if_needed, is_admin
from fpstune.utils.logger import setup_logging
from fpstune.utils.runtime import frontend_dist, frontend_source, is_frozen

if TYPE_CHECKING:
    import types

# ---------------------------------------------------------------------------
# Re-export names that external code (including tests) patches on fpstune.cli
# ---------------------------------------------------------------------------
from fpstune.utils.detect import get_gpu_info as get_gpu_info  # noqa: F401
from fpstune.utils.detect import get_os_info as get_os_info  # noqa: F401

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


def _write_pid_file(pid: int) -> None:
    try:
        with open(_get_pid_file(), "w") as f:
            f.write(str(pid))
    except OSError:
        pass


def _remove_pid_file() -> None:
    import contextlib
    import os

    with contextlib.suppress(OSError):
        os.unlink(_get_pid_file())


def _read_pid_file() -> int | None:
    try:
        with open(_get_pid_file()) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _is_fpstune_process(pid: int) -> bool:
    """Return True only if pid's command line contains 'fpstune'.

    Uses PowerShell / WMI to read the command line without importing psutil.
    Never returns True for a PID that doesn't match — fails safe to False.
    """
    import subprocess

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' -ErrorAction SilentlyContinue).CommandLine",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        cmdline = result.stdout.strip().lower()
        return bool(cmdline) and "fpstune" in cmdline
    except Exception:
        return False


def _kill_pid_tree(pid: int) -> bool:
    """Kill a process and its full child tree on Windows. Returns True on success."""
    import subprocess

    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _kill_previous_instance() -> bool:
    """Surgically kill the previous fpstune serve process.

    Strategy 1 — PID file: fast, uses stored PID from last run.
    Strategy 2 — Lock port: find the PID holding port 59471 via netstat.

    In both cases the PID is confirmed to be fpstune before killing.
    Unrelated processes (different command line) are never touched.
    Returns True if a previous instance was found and killed.
    """
    import subprocess

    killed = False

    # Strategy 1: PID file from the previous run
    pid = _read_pid_file()
    if pid and _is_fpstune_process(pid):
        killed = _kill_pid_tree(pid)

    if not killed:
        # Strategy 2: Scan netstat for the lock port owner
        try:
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if f":{_LOCK_PORT}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid_str = parts[-1] if parts else ""
                    if pid_str.isdigit():
                        candidate = int(pid_str)
                        if _is_fpstune_process(candidate):
                            killed = _kill_pid_tree(candidate)
                            break
        except Exception:
            pass

    return killed


def _find_free_port(preferred: int, max_attempts: int = 10) -> int:
    """Return the first available TCP port starting from preferred."""
    for port in range(preferred, preferred + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return preferred


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
        fpstune benchmark Measure this machine, before and after
        fpstune cleanup   Free disk space
        fpstune serve     Start the web UI (same as no args)

    \b
    Applying is done from the web UI, which is the only path that verifies
    each change actually took effect.
    """
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
        result = sp.run(["shutdown", "/a"], capture_output=True, text=True)
        if result.returncode == 0:
            console.print("[green]\u2713[/] Scheduled reboot cancelled")
        else:
            console.print("[yellow]![/] No scheduled reboot to cancel")
        return

    console.print(f"[bold yellow]System will reboot to BIOS in {delay} seconds![/]")
    console.print("[dim]Run 'fpstune bios --cancel' to abort[/]\n")

    result = sp.run(
        ["shutdown", "/r", "/fw", "/t", str(delay)],
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
@click.option("--ui-port", default=5173, help="Frontend dev server port")
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
@click.option("--api-only", is_flag=True, help="Only start API server (no frontend)")
def serve(port: int, ui_port: int, no_browser: bool, api_only: bool) -> None:
    """Start the fpstune web UI.

    A packaged build serves the UI from inside the executable and runs the API
    in this process. A source checkout runs the API and the Vite dev server as
    child processes, so both reload on edit.

    \b
    Examples:
        fpstune serve              # start everything, open the browser
        fpstune serve --api-only   # API only
        fpstune serve --no-browser # don't open the browser
    """
    import os

    ui.print_banner()

    if not _claim_single_instance():
        raise SystemExit(1)
    _write_pid_file(os.getpid())

    port = _find_free_port(port)

    if not _ensure_administrator():
        return

    if is_frozen():
        _serve_packaged(port=port, no_browser=no_browser)
    else:
        _serve_from_source(port=port, ui_port=ui_port, no_browser=no_browser, api_only=api_only)


def _claim_single_instance() -> bool:
    """Take the single-instance lock, replacing an older instance if there is one."""
    import time

    global _lock_sock
    _lock_sock = _acquire_instance_lock()
    if _lock_sock is not None:
        return True

    ui.step("Another fpstune is already running", "shutting it down")
    if _kill_previous_instance():
        time.sleep(1.5)  # let the OS release the port
        _lock_sock = _acquire_instance_lock()

    if _lock_sock is None:
        ui.fail("Could not take the instance lock")
        ui.hint(
            [
                "Close the other fpstune window",
                "If none is open, wait a few seconds and try again",
            ]
        )
        return False

    ui.ok("Replaced the previous instance")
    return True


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


def _serve_packaged(*, port: int, no_browser: bool) -> None:
    """Run the API in this process and serve the UI bundled beside it.

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


def _serve_from_source(*, port: int, ui_port: int, no_browser: bool, api_only: bool) -> None:
    """Run the API and the Vite dev server as children, so both reload on edit."""
    import signal
    import subprocess
    import time
    import webbrowser

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    frontend_dir = frontend_source()

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
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        processes.append(("API", api_process))
        ui.ok("API started", f"http://127.0.0.1:{port}")
    except OSError as e:
        ui.fail("Could not start the API", str(e))
        return

    if not api_only and frontend_dir is not None:
        if not (frontend_dir / "node_modules").exists():
            ui.step("Installing frontend dependencies", "first run only")
            install = subprocess.run(
                ["npm", "install"],
                cwd=frontend_dir,
                capture_output=True,
                text=True,
                shell=sys.platform == "win32",
                encoding="utf-8",
                errors="replace",
            )
            if install.returncode != 0:
                ui.warn("npm install failed", "continuing; the dev server may not start")

        ui.step(f"Starting the frontend on port {ui_port}")
        try:
            frontend_process = subprocess.Popen(
                ["npm", "run", "dev", "--", "--port", str(ui_port)],
                cwd=frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=sys.platform == "win32",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            processes.append(("Frontend", frontend_process))
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


if __name__ == "__main__":
    main()
