"""One lock that says "fpstune is busy doing something to this machine".

An apply, a cleanup and a benchmark must never overlap. The first two change the
machine; the third measures it. A measurement taken while a bulk apply is
halfway through describes neither the before nor the after, and it is
indistinguishable from a good one afterwards — which is the class of number C11
exists to refuse.

**Why this is not `game_config_writer.file_lock`.** That function is the same
primitive and is already reusable — it takes an arbitrary name — but it is built
for a different question. A config writer that finds the lock held *must wait*,
because its job is to write; so it blocks for 15 seconds and raises on timeout.
A scheduler that finds the lock held must do the opposite: give up instantly and
try again on the next tick, because a benchmark deferred by a minute is free and
a scheduler thread parked for 15 seconds every tick is not. Passing a timeout
into that function would mean editing `settings/executors/`, so the primitive is
rebuilt here with the acquire semantics this side needs.

The two should become one function taking a timeout. Left as a note rather than
done here because the edit lands in another module's file, and a lock is the
worst possible thing to refactor blind.

The frontend's `busyOperations` counter is the UI's view of the same fact and is
not the authority: it lives in one browser tab, and the CLI, a second tab and
this scheduler are all outside it.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
import threading
from collections.abc import Generator
from ctypes import wintypes
from typing import Any

from fpstune.utils.logger import get_logger

logger = get_logger()

OPERATION_MUTEX = "Global\\fpstune-machine-operation"
"""The one name every mutating or measuring operation takes.

`Global\\` so it holds across sessions and processes: the CLI, the API and a
second copy of the exe are all separate processes, and a lock that only covered
this one would be a lock that covers nothing on the day it matters.

One name for the whole class rather than one per operation, because the point is
mutual exclusion between *different* kinds of work. Two benches must not overlap
either, and they would share a name anyway.
"""

_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080
_WAIT_TIMEOUT = 0x00000102

_TRY_ONLY = 0
"""Milliseconds to wait: none. Held means held, and the caller comes back later."""

# The fallback when there is no Windows mutex to take: same process only. Never
# a silent no-op — a lock that does nothing turns a loud collision into a quiet
# wrong number, which is the whole failure this module exists to prevent.
_fallback_locks: dict[str, threading.Lock] = {}
_fallback_guard = threading.Lock()


def _fallback_lock(name: str) -> threading.Lock:
    with _fallback_guard:
        return _fallback_locks.setdefault(name, threading.Lock())


def _try_take_system_mutex(name: str) -> tuple[Any, Any] | None:
    """Take the named system mutex if it is free right now, else None.

    None means one of two things and the caller treats them alike: there is no
    such primitive here (not Windows), or somebody else is holding it. Both end
    in "not now", which is the only answer a poll loop can act on.

    The API object comes back beside the handle so the release happens on the
    same ``kernel32`` the wait was made on, and so the whole Win32 surface of
    this module stays in one function.
    """
    if sys.platform != "win32":
        return None

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = (wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        logger.debug("operation mutex unavailable (%s); serializing in-process only", name)
        return None

    waited = kernel32.WaitForSingleObject(handle, _TRY_ONLY)
    if waited == _WAIT_ABANDONED:
        # The previous holder died mid-operation. The lock is ours; whatever it
        # was doing is somebody else's problem and is not made better by waiting.
        logger.debug("operation lock %s was abandoned by a previous holder", name)
    elif waited != _WAIT_OBJECT_0:
        kernel32.CloseHandle(handle)
        return None
    return kernel32, handle


class _Held:
    """A taken lock, and the one way to give it back."""

    def __init__(self, release: Any) -> None:
        self._release = release

    def release(self) -> None:
        self._release()


def try_acquire(name: str = OPERATION_MUTEX) -> _Held | None:
    """Take the operation lock if it is free, or answer None immediately.

    Never blocks. A caller that finds it held is expected to do nothing and ask
    again later — queueing would mean a backlog of measurements all describing a
    machine that has since changed.
    """
    held = _try_take_system_mutex(name)
    if held is not None:
        kernel32, handle = held

        def _release_system() -> None:
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)

        return _Held(_release_system)

    if sys.platform == "win32":
        # A real Windows mutex existed and somebody else has it. Falling through
        # to the process-local lock here would report the machine free while
        # another process was mid-apply.
        return None

    local = _fallback_lock(name)
    if not local.acquire(blocking=False):
        return None
    return _Held(local.release)


def is_free(name: str = OPERATION_MUTEX) -> bool:
    """Whether the lock could be taken right now.

    Take-and-release rather than a peek, because Windows offers no peek and one
    invented out of a wait plus a release is the same thing with a longer name.
    Inherently a snapshot: it is true until somebody else acts on it, which is
    why the scheduler *holds* the lock for its run rather than checking it and
    hoping.
    """
    held = try_acquire(name)
    if held is None:
        return False
    held.release()
    return True


@contextlib.contextmanager
def operation_lock(name: str = OPERATION_MUTEX) -> Generator[bool, None, None]:
    """Hold the operation lock for a block, or report that it could not be had.

    Yields whether it was taken, rather than raising or blocking. The caller is
    a poll loop and "not now" is an ordinary answer for it, not an error:

        with operation_lock() as taken:
            if not taken:
                return DEFERRED_BUSY
            ...
    """
    held = try_acquire(name)
    try:
        yield held is not None
    finally:
        if held is not None:
            held.release()
