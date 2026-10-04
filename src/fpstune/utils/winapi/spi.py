"""SystemParametersInfoW for the per-user input and animation values.

Writing the registry alone changes nothing until the next sign-in: the live
values sit in win32k and are re-read from the profile only at logon, so a
setting read back as applied while the pointer still accelerated. These calls
bring the running session in line. They pass SPIF_SENDCHANGE without
SPIF_UPDATEINIFILE wherever fpstune writes the registry value itself, because
the profile to persist into is the console user's (``session.registry_root``),
which is not always the elevated token's own. Constants from winuser.h.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

SPI_GETMOUSE = 0x0003
SPI_SETMOUSE = 0x0004
SPI_GETFILTERKEYS = 0x0032
SPI_SETFILTERKEYS = 0x0033
SPI_GETTOGGLEKEYS = 0x0034
SPI_SETTOGGLEKEYS = 0x0035
SPI_GETSTICKYKEYS = 0x003A
SPI_SETSTICKYKEYS = 0x003B
SPI_GETANIMATION = 0x0048
SPI_SETANIMATION = 0x0049
SPI_GETCLIENTAREAANIMATION = 0x1042
SPI_SETCLIENTAREAANIMATION = 0x1043

SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

# Each accessibility structure starts {cbSize, dwFlags}; FILTERKEYS carries four
# more DWORDs (wait, delay, repeat, bounce), which a read-modify-write keeps.
STICKYKEYS = (SPI_GETSTICKYKEYS, SPI_SETSTICKYKEYS, 2)
FILTERKEYS = (SPI_GETFILTERKEYS, SPI_SETFILTERKEYS, 6)
TOGGLEKEYS = (SPI_GETTOGGLEKEYS, SPI_SETTOGGLEKEYS, 2)


def _spi() -> Any:
    function = ctypes.WinDLL("user32", use_last_error=True).SystemParametersInfoW
    function.argtypes = (wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT)
    function.restype = wintypes.BOOL
    return function


def _call(action: int, ui_param: int, pv_param: object, flags: int) -> bool:
    return bool(_spi()(action, ui_param, pv_param, flags))


def set_mouse(threshold1: int, threshold2: int, acceleration: int) -> bool:
    """SPI_SETMOUSE: the three values behind "Enhance pointer precision"."""
    values = (ctypes.c_int * 3)(threshold1, threshold2, acceleration)
    return _call(SPI_SETMOUSE, 0, ctypes.byref(values), SPIF_SENDCHANGE)


def set_access_flags(structure: tuple[int, int, int], flags: int) -> bool:
    """Read an accessibility structure, replace its dwFlags, write it back."""
    get, put, dwords = structure
    buffer = (wintypes.DWORD * dwords)()
    size = ctypes.sizeof(buffer)
    buffer[0] = size
    if not _call(get, size, ctypes.byref(buffer), 0):
        return False
    buffer[1] = flags
    return _call(put, size, ctypes.byref(buffer), SPIF_SENDCHANGE)


def animations() -> tuple[bool, bool] | None:
    """(window animation on, client-area animation on), or None when unreadable."""
    info = (ctypes.c_uint * 2)(8, 0)  # ANIMATIONINFO {cbSize, iMinAnimate}
    client = wintypes.BOOL()
    if not _call(SPI_GETANIMATION, 8, ctypes.byref(info), 0):
        return None
    if not _call(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(client), 0):
        return None
    return bool(info[1]), bool(client.value)


def set_animations(on: bool) -> bool:
    """Window and client-area animations together, as Settings' one switch does.

    The client-area flag has no registry value of its own — Windows packs it
    into UserPreferencesMask — so it is the one call here that persists through
    SPIF_UPDATEINIFILE.
    """
    info = (ctypes.c_uint * 2)(8, int(on))
    window = _call(SPI_SETANIMATION, 8, ctypes.byref(info), SPIF_SENDCHANGE)
    # The BOOL travels in pvParam itself, not behind a pointer.
    client = _call(
        SPI_SETCLIENTAREAANIMATION,
        0,
        ctypes.c_void_p(int(on)),
        SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
    )
    return window and client
