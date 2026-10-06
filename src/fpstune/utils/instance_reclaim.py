"""Closing a previous fpstune that still holds the instance lock but answers no HTTP.

``utils/instances.py`` asks every fpstune it can find over ``/health`` to stop,
and that is always tried first. This is the fallback for what is left: an old
instance whose server is gone or hung — two ``python.exe`` processes (a launcher
and its child) that serve no HTTP port while one of them still has the lock
socket bound.

Finding them. The kernel's socket table (``GetExtendedTcpTable``) names the
owning PID of any listening or connected socket, and that is tried first. It does
**not** list a socket that is only bound: measured on Windows 11, a bound socket
that never listened is absent from the ``TCP_TABLE_OWNER_PID_ALL`` table while a
second ``bind`` to it fails with WSAEADDRINUSE. The lock of every release up to
now is exactly that (it binds and never listens), so when the table shows no
owner the fallback is every *server-shaped* fpstune process on the machine —
fpstune started to serve, which is what the owner asked for ("a new start closes
ALL previous ones"). A bare ``fpstune status`` or ``benchmark`` in another window
is not a server and is left running.

Four rules, in order of how much damage skipping them would do:

1. **A stranger is never touched.** A process is ended only when its executable
   and command line show fpstune: the ``fpstune.exe`` (the frozen build and the
   pip/uv launcher share the name), or a Python running ``-m fpstune[.x]`` / a
   script named ``fpstune``. A plain ``python.exe`` running something else, an
   unrelated exe, a process whose image cannot be read — never. When the table
   names the owner and it is a stranger, the start refuses and the message names
   the PID and image.
2. **Only the fpstune tree goes.** The server, its fpstune children, and an
   fpstune parent whose only fpstune child is the one being ended (the launcher
   over its API child, the PyInstaller bootloader over its runtime), each
   verified the same way. A process that is not fpstune is never ended because it
   is near one.
3. **Never this process or its ancestors.** A start launched by a shim must not
   end the shim that launched it.
4. **Every PID ended is logged with why**, and each is verified again just before
   it is ended, so a PID the system reused in between is not.

Everything the machine answers goes through ``System``, so the decisions are
tested on a pretend machine; ``WindowsSystem`` is the real one, over ``ctypes``
(``utils/winapi/processes.py``) — numbers and paths, no command output text.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PureWindowsPath
from typing import Literal, Protocol

from fpstune.utils.logger import get_logger
from fpstune.utils.winapi import processes

logger = get_logger()

_FPSTUNE_EXE = "fpstune.exe"
_PYTHON_IMAGE = re.compile(r"^pythonw?(\d+(\.\d+)*)?\.exe$")
_FPSTUNE_SCRIPTS = frozenset({"fpstune", "fpstune.exe", "fpstune-script.py", "fpstune-script.pyw"})
_FPSTUNE_ENTRY_FILES = frozenset({"cli.py", "__main__.py"})
_OPTIONS_WITH_A_VALUE = frozenset({"-X", "-W"})
_SERVER_MODULES = frozenset({"fpstune.api.serving"})
_CLI_MODULES = frozenset({"fpstune", "fpstune.cli", "fpstune.__main__"})
_INFO_FLAGS = frozenset({"--help", "-h", "--version"})
_EXIT_GRACE_SECONDS = 2.0
_EXIT_POLL_SECONDS = 0.05


class System(Protocol):
    """What the machine can be asked; ``WindowsSystem`` answers for the real one."""

    def own_pid(self) -> int: ...
    def lock_owner_pids(self, port: int) -> list[int]: ...
    def list_processes(self) -> list[processes.ProcessEntry]: ...
    def image_path(self, pid: int) -> str | None: ...
    def command_line(self, pid: int) -> str | None: ...
    def creation_time(self, pid: int) -> int | None: ...
    def has_exited(self, pid: int) -> bool: ...
    def terminate(self, pid: int) -> str: ...


class WindowsSystem:
    def own_pid(self) -> int:
        return os.getpid()

    def lock_owner_pids(self, port: int) -> list[int]:
        return processes.socket_owner_pids(port)

    def list_processes(self) -> list[processes.ProcessEntry]:
        return processes.list_processes()

    def image_path(self, pid: int) -> str | None:
        return processes.image_path(pid)

    def command_line(self, pid: int) -> str | None:
        return processes.command_line(pid)

    def creation_time(self, pid: int) -> int | None:
        return processes.creation_time(pid)

    def has_exited(self, pid: int) -> bool:
        return processes.has_exited(pid)

    def terminate(self, pid: int) -> str:
        return processes.terminate(pid)


@dataclass(frozen=True)
class Verdict:
    """Whether one process is fpstune, with the image it was judged by."""

    pid: int
    is_fpstune: bool
    image: str
    reason: str
    serves: bool = False
    """fpstune *and* started to serve (a bare ``fpstune``/``serve``, or the API module)."""


@dataclass(frozen=True)
class Ended:
    pid: int
    image: str
    why: str
    outcome: str
    """``ended``, ``already_gone`` or ``failed``."""

    def describe(self) -> str:
        return f"PID {self.pid} ({self.image}): {self.why} — {self.outcome.replace('_', ' ')}"


@dataclass(frozen=True)
class Reclaimed:
    """What reclaiming the lock port did."""

    status: Literal["no_holder", "refused", "ended", "failed"]
    message: str
    holder_pid: int | None = None
    holder_image: str = ""
    ended: tuple[Ended, ...] = field(default_factory=tuple)


def _cli_serves(args: Sequence[str]) -> bool:
    """fpstune's own CLI serves unless it was handed another subcommand or an info flag."""
    for arg in args:
        if arg in _INFO_FLAGS:
            return False
        if not arg.startswith("-"):
            return arg == "serve"
    return True


def _script_is_fpstune(script: str) -> bool:
    path = PureWindowsPath(script)
    name = path.name.casefold()
    if name in _FPSTUNE_SCRIPTS:
        return True
    return name in _FPSTUNE_ENTRY_FILES and path.parent.name.casefold() == "fpstune"


def python_invocation(argv: Sequence[str]) -> bool | None:
    """None when a Python command line is not fpstune, else whether it serves.

    fpstune is ``-m fpstune[.x]`` or a script named like fpstune. Only the first
    thing Python is told to run counts, so ``python -m pip install fpstune`` and
    ``python other.py fpstune`` are not fpstune.
    """
    args = list(argv[1:])
    index = 0
    while index < len(args):
        arg = args[index]
        module = None
        rest: list[str] = []
        if arg == "-m":
            module = args[index + 1] if index + 1 < len(args) else ""
            rest = args[index + 2 :]
        elif arg.startswith("-m") and len(arg) > 2:
            module, rest = arg[2:], args[index + 1 :]
        if module is not None:
            if module in _SERVER_MODULES:
                return True
            if module in _CLI_MODULES:
                return _cli_serves(rest)
            return False if module.startswith("fpstune.") else None
        if arg.startswith("-c"):
            return None
        if arg in _OPTIONS_WITH_A_VALUE:
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            return _cli_serves(args[index + 1 :]) if _script_is_fpstune(arg) else None
    return None


def judge(pid: int, image: str | None, argv: Sequence[str] | None) -> Verdict:
    """Decide from the executable path and command line whether ``pid`` is fpstune."""
    if not image:
        return Verdict(pid, False, "(unreadable)", "its executable path could not be read")
    name = PureWindowsPath(image).name.casefold()
    if name == _FPSTUNE_EXE:
        serves = argv is not None and _cli_serves(argv[1:])
        return Verdict(pid, True, image, "the fpstune executable", serves)
    if _PYTHON_IMAGE.match(name):
        if argv is None:
            return Verdict(pid, False, image, "a Python whose command line could not be read")
        invocation = python_invocation(argv)
        if invocation is None:
            return Verdict(pid, False, image, "a Python running something other than fpstune")
        return Verdict(pid, True, image, "a Python running fpstune", invocation)
    return Verdict(pid, False, image, "an executable that is not fpstune")


def _could_be_fpstune(exe_name: str) -> bool:
    name = exe_name.casefold()
    return name == _FPSTUNE_EXE or bool(_PYTHON_IMAGE.match(name))


class _Reclaimer:
    def __init__(self, system: System) -> None:
        self.system = system
        self.entries = {entry.pid: entry for entry in system.list_processes()}
        self.children: dict[int, list[int]] = {}
        for entry in self.entries.values():
            self.children.setdefault(entry.parent_pid, []).append(entry.pid)
        self._verdicts: dict[int, Verdict] = {}
        self.protected = self._own_lineage()

    def _own_lineage(self) -> set[int]:
        """This process and every ancestor of it."""
        pid: int | None = self.system.own_pid()
        lineage: set[int] = set()
        while pid and pid not in lineage:
            lineage.add(pid)
            entry = self.entries.get(pid)
            pid = entry.parent_pid if entry else None
        return lineage

    def verdict(self, pid: int, *, fresh: bool = False) -> Verdict:
        if fresh or pid not in self._verdicts:
            image = self.system.image_path(pid)
            line = None
            if image and _could_be_fpstune(PureWindowsPath(image).name):
                text = self.system.command_line(pid)
                line = None if text is None else processes.split_command_line(text)
            self._verdicts[pid] = judge(pid, image, line)
        return self._verdicts[pid]

    def servers(self) -> list[int]:
        """Every fpstune on the machine that started to serve, other than this start's own line."""
        return [
            entry.pid
            for entry in self.entries.values()
            if entry.pid not in self.protected
            and _could_be_fpstune(entry.exe_name)
            and self.verdict(entry.pid).serves
        ]

    def _fpstune_children(self, pid: int) -> list[int]:
        return [
            child
            for child in self.children.get(pid, [])
            if child not in self.protected and self.verdict(child).is_fpstune
        ]

    def plan(self, owner: int, owner_why: str) -> list[tuple[int, str]]:
        """``(pid, why)`` in the order they should end: descendants, the owner, then ancestors."""
        descendants: list[tuple[int, str]] = []
        queue = [owner]
        while queue:
            parent = queue.pop(0)
            for child in self._fpstune_children(parent):
                descendants.append((child, f"an fpstune child of PID {parent}"))
                queue.append(child)
        ordered = list(reversed(descendants))
        ordered.append((owner, owner_why))

        planned = {pid for pid, _ in ordered}
        current = owner
        while True:
            entry = self.entries.get(current)
            parent = entry.parent_pid if entry else 0
            if not parent or parent in self.protected or parent in planned:
                break
            if not self.verdict(parent).is_fpstune or not self._started_before(parent, current):
                break
            if any(child not in planned for child in self._fpstune_children(parent)):
                break  # it supervises something else of fpstune's too
            ordered.append((parent, f"the fpstune parent supervising PID {current}"))
            planned.add(parent)
            current = parent
        return ordered

    def _started_before(self, parent: int, child: int) -> bool:
        """A reused PID names a newer process than its supposed child; unknown times pass."""
        parent_time = self.system.creation_time(parent)
        child_time = self.system.creation_time(child)
        if parent_time is None or child_time is None:
            return True
        return parent_time <= child_time


def _leaves_the_process_list(system: System, pid: int) -> bool:
    """Whether ``pid`` is gone, allowing a moment for one that is on its way out.

    A launcher exits by itself once its child is ended; until whoever started it
    lets go of its handle it stays listed, exited, and can no longer be opened.
    """
    deadline = time.monotonic() + _EXIT_GRACE_SECONDS
    while True:
        if system.has_exited(pid) or all(e.pid != pid for e in system.list_processes()):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_EXIT_POLL_SECONDS)


def _end(reclaimer: _Reclaimer, pid: int, why: str) -> Ended:
    """End one planned process, after looking at it once more."""
    system = reclaimer.system
    now = reclaimer.verdict(pid, fresh=True)
    if now.is_fpstune:
        outcome = system.terminate(pid)
    elif not system.image_path(pid) and _leaves_the_process_list(system, pid):
        outcome = "already_gone"
    else:
        outcome = "failed"
        logger.warning("PID %d no longer looks like fpstune (%s); left alone", pid, now.reason)
    logger.info("fpstune takeover: PID %d (%s) %s — %s", pid, now.image, outcome, why)
    return Ended(pid, now.image, why, outcome)


def _refusal(reclaimer: _Reclaimer, port: int, owners: list[int]) -> Reclaimed | None:
    """A refusal naming the first socket owner that is a stranger (or ourselves), if any."""
    for pid in owners:
        verdict = reclaimer.verdict(pid)
        if verdict.is_fpstune and pid not in reclaimer.protected:
            continue
        why = (
            "it is this process or one that started it"
            if pid in reclaimer.protected
            else verdict.reason
        )
        return Reclaimed(
            "refused",
            f"127.0.0.1:{port} is held by PID {pid} ({verdict.image}), "
            f"which is not an fpstune to end: {why}. Left alone.",
            holder_pid=pid,
            holder_image=verdict.image,
        )
    return None


def reclaim_lock_holder(port: int, *, system: System | None = None) -> Reclaimed:
    """End the fpstune process tree(s) behind ``port``, or refuse and say why.

    Called only after the polite ``/health`` stop was tried and the lock is
    still held. Never raises for a machine that cannot answer: that is a
    ``failed`` result carrying the reason.
    """
    system = system or WindowsSystem()
    ended: list[Ended] = []
    try:
        owners = [pid for pid in system.lock_owner_pids(port) if pid != system.own_pid()]
        reclaimer = _Reclaimer(system)
        if owners:
            refusal = _refusal(reclaimer, port, owners)
            if refusal is not None:
                return refusal
            targets = [(pid, "owns the lock port and answers no /health") for pid in owners]
        else:
            targets = [
                (pid, "an fpstune server that answered no stop request")
                for pid in reclaimer.servers()
            ]
        if not targets:
            return Reclaimed(
                "no_holder",
                "No fpstune process is serving, and the socket table names no owner of "
                f"127.0.0.1:{port} (a bound socket that never listened is not in it)",
            )
        for owner, owner_why in targets:
            for pid, why in reclaimer.plan(owner, owner_why):
                if all(done.pid != pid for done in ended):
                    ended.append(_end(reclaimer, pid, why))
    except OSError as exc:
        return Reclaimed(
            "failed",
            f"Could not read the processes holding 127.0.0.1:{port}: {exc}",
            ended=tuple(ended),
        )

    first = reclaimer.verdict(targets[0][0])
    failed = [done for done in ended if done.outcome == "failed"]
    if failed:
        return Reclaimed(
            "failed",
            "Could not end every fpstune process holding the lock: "
            + "; ".join(done.describe() for done in failed),
            holder_pid=first.pid,
            holder_image=first.image,
            ended=tuple(ended),
        )
    return Reclaimed(
        "ended",
        f"Ended {len(ended)} fpstune process(es) behind 127.0.0.1:{port}",
        holder_pid=first.pid,
        holder_image=first.image,
        ended=tuple(ended),
    )
