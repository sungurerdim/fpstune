"""The timeout `run_powershell` promises is the one it keeps.

A PowerShell command that starts another process hands that process its stdout
and stderr pipes, and killing PowerShell does not take them back. `subprocess.run`
reaps a timed-out child with a `communicate()` that takes no timeout, so the call
blocked until the grandchild exited — which for `dism.exe` meant tens of minutes,
and for the cleanup size that started it meant a "calculating" that never ended
and a UI polling for a number nobody was going to produce.
"""

from __future__ import annotations

import sys
import time

import pytest

from fpstune.utils.powershell import run_powershell

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="the PowerShell runner is Windows-only"
)

# Long enough that a run which waits for the grandchild is unmistakable, short
# enough that the process it leaves behind is gone before the suite ends.
_GRANDCHILD_SECONDS = 20
_TIMEOUT = 3


def test_timeout_is_honoured_when_a_grandchild_holds_the_pipes() -> None:
    """Return at the timeout, not when whatever PowerShell started finishes."""
    # `-NoNewWindow` makes ping inherit this PowerShell's handles — the same way
    # `dism.exe` inherits them inside the cleanup-size script — and it outlives
    # the PowerShell that started it.
    command = (
        f"Start-Process -NoNewWindow -FilePath 'ping' "
        f"-ArgumentList '-n','{_GRANDCHILD_SECONDS}','127.0.0.1'; "
        f"Start-Sleep -Seconds {_GRANDCHILD_SECONDS}"
    )

    start = time.monotonic()
    ok, output = run_powershell(command, timeout=_TIMEOUT)
    elapsed = time.monotonic() - start

    assert ok is False
    assert "timed out" in output
    # Half the grandchild's life: comfortably above the timeout plus PowerShell's
    # start-up, and comfortably below "waited for the grandchild".
    assert elapsed < _GRANDCHILD_SECONDS / 2, (
        f"run_powershell(timeout={_TIMEOUT}) returned after {elapsed:.1f}s — "
        "it waited for the process its child left behind"
    )
