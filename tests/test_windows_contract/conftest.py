"""Shared harness for running shipped PowerShell commands against a described host.

The point of every test in this directory is to exercise the command fpstune
actually ships, not a copy of its logic — a copy only ever proves the copy works,
which is how seven defects survived a green suite. To do that against controlled
inputs, the tests shadow the cmdlets a command calls with functions of the same
name (a function wins over a cmdlet in the same session) and describe the fake
host as JSON.

This module owns the mechanical half: write the script and the payload, run
PowerShell, hand back the last line it printed.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# The command swallows every failure as its default value, which is right in
# production and useless in a test: a broken harness becomes indistinguishable
# from a correct negative result. Tests rewrite the catch body to this prefix so a
# failure is loud, and assert the clause they rewrite still exists.
HARNESS_ERROR = "HARNESS_ERROR"


def run_shipped_script(script: str, payload: dict[str, Any], *, expect_exit: int = 0) -> str:
    """Run `script` with `payload` exposed as JSON via $env:FPSTUNE_FAKE_HOST.

    Returns the whole of stdout. Use this for a script whose answer is a document
    (ConvertTo-Json output, a table); `run_shipped_command` is the one-line form
    executors read. A script that reports failure with `exit 1` on purpose is
    checked against `expect_exit`, so the exit code is part of the contract too.
    """
    with tempfile.TemporaryDirectory() as tmp:
        payload_path = Path(tmp) / "host.json"
        script_path = Path(tmp) / "command.ps1"
        payload_path.write_text(json.dumps(payload), encoding="utf-8")
        script_path.write_text(script, encoding="utf-8")

        result = subprocess.run(  # noqa: S603 - fixed argv, both paths are ours
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env={**os.environ, "FPSTUNE_FAKE_HOST": str(payload_path)},
            check=False,
        )

    assert result.returncode == expect_exit, (
        f"exit {result.returncode}, expected {expect_exit}: {result.stdout[:500]} {result.stderr[:1500]}"
    )
    assert result.stdout.strip(), f"script produced no output. stderr: {result.stderr[:500]}"
    return result.stdout


def run_shipped_command(script: str, payload: dict[str, Any]) -> str:
    """Run `script` and hand back the last non-empty stdout line.

    That line is what the executor reads as the detected value.
    """
    lines = [
        line.strip() for line in run_shipped_script(script, payload).splitlines() if line.strip()
    ]
    answer = lines[-1]
    assert not answer.startswith(HARNESS_ERROR), (
        f"The command threw instead of evaluating, so this result proves nothing: {answer}"
    )
    return answer


def loud_catch(command: str, shipped_catch: str) -> str:
    """Replace a swallowing catch clause so harness failures cannot pass as results."""
    assert shipped_catch in command, (
        f"The catch clause this test rewrites is gone ({shipped_catch!r}). Without it a "
        "broken harness reads as a legitimate result again."
    )
    return command.replace(shipped_catch, f"catch {{ '{HARNESS_ERROR}: ' + $_.Exception.Message }}")


def fake_adapters(*adapters: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Get-NetAdapter-shaped objects, defaulting to an active physical NIC."""
    return [
        {
            "Name": adapter.get("name", f"Adapter{index}"),
            "ifIndex": adapter["ifIndex"],
            "InterfaceGuid": adapter.get("guid", f"{{guid-{adapter['ifIndex']}}}"),
            "InterfaceOperationalStatus": adapter.get("status", 1),
            "Virtual": adapter.get("virtual", False),
            "InterfaceDescription": adapter.get("description", "Realtek Gaming Ethernet"),
        }
        for index, adapter in enumerate(adapters)
    ]
