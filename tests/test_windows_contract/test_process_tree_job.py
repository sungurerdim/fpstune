"""The Job Object sees and stops the whole tree, grandchildren included.

`run_powershell` used to kill PowerShell and leave `Dism.exe` running with the
pipe held for twenty minutes (utils/powershell.py). A stall must stop what is
actually stuck, and progress must be read from the process doing the work, which
is often a level below the one fpstune started.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from fpstune.utils.process_watch import StallPolicy, run_watched

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Job Objects are Windows-only")

# A child that starts a silent grandchild, reports its pid, and waits on it.
_PARENT = (
    "import subprocess, sys\n"
    "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "print(g.pid, flush=True)\n"
    "g.wait()\n"
)


def _alive(pid: int) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
    ).stdout
    return str(pid) in out


def test_a_stall_stops_the_grandchild_too() -> None:
    policy = StallPolicy("contract", stall_s=3.0, sample_s=0.5)
    result = run_watched([sys.executable, "-c", _PARENT], policy)
    assert result.timed_out
    grandchild = int(result.stdout.split()[0])
    time.sleep(1)
    assert not _alive(grandchild), "the grandchild survived the stall"


def test_a_grandchild_writing_silently_counts_as_progress() -> None:
    """The parent prints nothing and only waits; the bytes move a level down."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "blob"
        writer = (
            "import time\n"
            f"f = open({str(target)!r}, 'wb')\n"
            "end = time.monotonic() + 6\n"
            "while time.monotonic() < end:\n"
            "    f.write(b'x' * 65536); f.flush(); time.sleep(0.05)\n"
        )
        parent = f"import subprocess, sys\nsubprocess.run([sys.executable, '-c', {writer!r}])\n"
        policy = StallPolicy("contract", stall_s=3.0, sample_s=0.5)
        result = run_watched([sys.executable, "-c", parent], policy)
    assert result.ok, result.reason
