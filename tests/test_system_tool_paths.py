"""Windows tools are started by absolute path, never by bare name.

fpstune runs as Administrator, typically from a Downloads folder. A bare
``"powershell"`` is resolved through the search path, which starts with the
launching executable's own folder, so a planted ``powershell.exe`` beside
fpstune.exe would run elevated. utils/system_tools.py answers with the System32
directory Windows reports.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "fpstune"

_TOOLS = {
    "powershell", "pwsh", "cmd", "netsh", "powercfg", "bcdedit", "taskkill", "tasklist",
    "sc", "reg", "netstat", "nvidia-smi", "wevtutil", "logman", "dism", "sfc", "schtasks",
    "ping", "tracert", "shutdown", "rstrui", "wmic", "fsutil", "defrag", "ipconfig",
    "vssadmin", "cleanmgr", "pnputil", "w32tm", "route", "arp", "nslookup", "explorer",
    "regedit",
}  # fmt: skip


def _bare(value: str) -> bool:
    name = value.lower().removesuffix(".exe")
    return name in _TOOLS


def test_no_command_list_starts_with_a_bare_tool_name() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        exported = {
            id(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.List) or not node.elts or id(node) in exported:
                continue
            first = node.elts[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and _bare(first.value)
            ):
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno} [{first.value!r}, ...]")
    assert offenders == [], "start these through utils/system_tools.py: " + ", ".join(offenders)


def test_tools_resolve_under_the_system_directory() -> None:
    from fpstune.utils.system_tools import powershell_exe, system32, system_tool

    assert system_tool("sc.exe").startswith(system32())
    assert powershell_exe().startswith(system32())
    assert powershell_exe().lower().endswith("powershell.exe")
