"""Apply actions that run in Python rather than as PowerShell text.

``ACTION_COMMANDS`` maps an ``apply_command`` key to a PowerShell script. Some
actions have no business in PowerShell: the standby-list purge needs a native
kernel call, and reaching ``ntdll`` from a script means compiling a C# class
with ``Add-Type`` — the pattern Windows Defender flags as trojan behaviour
(2026-09-02). Those actions live here as plain functions with the same contract
the executor already speaks, ``(ok, message)``, and the executor consults this
table before it ever builds a command line.

An action's message is what the user reads after apply, so it states what was
measured on this machine and never a figure from somewhere else (C11).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fpstune.utils.winapi.memory import purge_standby_list

PythonAction = Callable[[dict[str, Any]], tuple[bool, str | None]]


def purge_standby(_args: dict[str, Any]) -> tuple[bool, str | None]:
    """Drop the standby list and report the megabytes it actually released."""
    outcome = purge_standby_list()
    if not outcome.ok:
        return False, (
            f"The kernel refused the standby-list purge (NTSTATUS {outcome.status:#010x}); "
            "it needs an elevated process holding SeProfileSingleProcessPrivilege"
        )
    if outcome.before is None or outcome.after is None:
        return True, "Standby list purged; the page counts could not be read to size it"
    return True, (
        f"Standby list purged: {outcome.released_mb} MB released "
        f"(standby {outcome.before.standby_mb} MB before, {outcome.after.standby_mb} MB after)"
    )


PYTHON_ACTIONS: dict[str, PythonAction] = {
    "purge_standby": purge_standby,
}
