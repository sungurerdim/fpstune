"""A stuck PowerShell ends on its stall, and takes what it started with it.

A PowerShell command that starts another process hands that process its stdout
and stderr pipes, and killing PowerShell does not take them back. The old runner
killed PowerShell alone and left `dism.exe` running with the pipe held for tens
of minutes. The watched runner stops the whole tree through its Job Object, and
only when nothing in it has moved for the policy's stall window.
"""

from __future__ import annotations

import sys
import time

import pytest

from fpstune.utils.powershell import run_powershell
from fpstune.utils.process_watch import StallPolicy

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="the PowerShell runner is Windows-only"
)

# Long enough that a run which waits for the grandchild is unmistakable.
_GRANDCHILD_SECONDS = 30
_STALL = StallPolicy("contract", stall_s=4.0, sample_s=0.5)


def test_a_silent_grandchild_holding_the_pipes_is_stopped_at_the_stall() -> None:
    """Return at the stall, not when whatever PowerShell started finishes."""
    # `-NoNewWindow` makes the child inherit this PowerShell's handles — the way
    # `dism.exe` inherits them inside the cleanup-size script — and it sleeps,
    # moving nothing, which is what stuck looks like.
    command = (
        "Start-Process -NoNewWindow -FilePath 'powershell' "
        f"-ArgumentList '-NoProfile','-Command','Start-Sleep -Seconds {_GRANDCHILD_SECONDS}'; "
        f"Start-Sleep -Seconds {_GRANDCHILD_SECONDS}"
    )

    start = time.monotonic()
    ok, output = run_powershell(command, _STALL)
    elapsed = time.monotonic() - start

    assert ok is False
    assert "no progress for" in output
    assert elapsed < _GRANDCHILD_SECONDS / 2, (
        f"run_powershell returned after {elapsed:.1f}s — it waited for the process "
        "its child left behind"
    )


def test_a_long_command_that_keeps_printing_is_not_stopped() -> None:
    """Twice the stall window of steady output must run to the end."""
    seconds = int(_STALL.stall_s * 2)
    command = f"1..{seconds} | ForEach-Object {{ $_; Start-Sleep -Seconds 1 }}"
    ok, output = run_powershell(command, _STALL)
    assert ok, output
    assert output.split()[-1] == str(seconds)
