"""What rate this machine's audio output actually runs at.

A game that mixes below its output device throws information away before Windows
ever sees it: 22050 Hz carries nothing above about 11 kHz, and the cues that tell
a player *where* a sound came from live in that band. So the rate a game should
mix at is a property of the hardware, exactly like the panel's refresh rate — not
a constant, and not a preference.

Read straight out of the registry rather than through PowerShell, because this is
session-stable data and C7 forbids spawning a process for it.
"""

from __future__ import annotations

import struct
import sys

from fpstune.utils.logger import get_logger

logger = get_logger()

_RENDER_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"

# PKEY_AudioEngine_DeviceFormat. The stored blob is not a bare WAVEFORMATEX: it
# carries an eight-byte property header first, which is why reading from offset 0
# yields a two-byte channel count of 0 and a sample rate of 1. The offset was
# confirmed against endpoints whose rate was already known rather than derived
# from documentation.
_DEVICE_FORMAT = "{f19f064d-082c-4e27-bc73-6882a1bb8e4c},0"
_FORMAT_OFFSET = 8

# DEVICE_STATE_ACTIVE. Unplugged and disabled endpoints keep their last format,
# so counting them would let a headset last used at 16 kHz decide the answer.
_STATE_ACTIVE = 1

# Anything outside this is a misread rather than a device: the struct offset
# being wrong produces values like 1 and 589822, and both used to get through.
_PLAUSIBLE = (8000, 384000)


def get_output_sample_rate_hz() -> int | None:
    """Return the highest sample rate among active render endpoints.

    Returns:
        Rate in Hz, or None when nothing could be read — which callers must treat
        as "not detected" rather than substituting 44100. A recommendation built
        from a guessed rate is the hardcoded-constant defect in a new place.
    """
    if sys.platform != "win32":
        return None

    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows only
        return None

    rates: list[int] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _RENDER_KEY) as root:
            count = winreg.QueryInfoKey(root)[0]
            for index in range(count):
                try:
                    endpoint = winreg.EnumKey(root, index)
                    with winreg.OpenKey(root, endpoint) as device:
                        if winreg.QueryValueEx(device, "DeviceState")[0] != _STATE_ACTIVE:
                            continue
                        with winreg.OpenKey(device, "Properties") as props:
                            blob = winreg.QueryValueEx(props, _DEVICE_FORMAT)[0]
                except OSError:
                    continue

                if not isinstance(blob, bytes) or len(blob) < _FORMAT_OFFSET + 16:
                    continue
                # WAVEFORMATEX: wFormatTag, nChannels, nSamplesPerSec, ...
                _tag, _channels, hz = struct.unpack_from("<HHI", blob, _FORMAT_OFFSET)
                if _PLAUSIBLE[0] <= hz <= _PLAUSIBLE[1]:
                    rates.append(hz)
    except OSError as exc:
        logger.debug("Audio endpoint enumeration failed: %s", exc)
        return None

    if not rates:
        logger.debug("No active audio render endpoint reported a usable format")
        return None

    return max(rates)
