"""Shared PowerShell execution helpers for system route modules."""

from __future__ import annotations

import asyncio

from fpstune.utils.powershell import escape_single_quoted, run_powershell

# Aliases preserved from the original routes/system.py module.
_escape_ps_string = escape_single_quoted
_run_powershell = run_powershell


async def _run_powershell_async(
    command: str, component: str = "system", timeout: int = 30
) -> tuple[bool, str]:
    """Run PowerShell asynchronously to avoid blocking the event loop."""
    result: tuple[bool, str | None] = await asyncio.to_thread(
        _run_powershell, command, timeout=timeout, component=component
    )
    return result[0], result[1] or ""
