"""What the panel itself declares, read from its EDID.

Two monitor facts used to be manufactured rather than read: the native refresh
rate was a copy of the highest mode EnumDisplaySettings listed, and VRR support
was the guess ``maxHz > 60`` — which turned driver V-Sync and a frame cap on
for a plain 75 Hz office panel (8-16 ms of latency the codebase's own comments
say to avoid) and told a 60 Hz FreeSync panel it had nothing. Both answers are
in the EDID, so both are read from it here and nowhere else.

The reading rules, and why they are these:

- **Native refresh** is the preferred Detailed Timing Descriptor — the first
  18-byte timing block, which EDID defines as the panel's preferred mode. It is
  a fact about the panel, not about what the GPU can drive it at, so it may
  legitimately differ from the mode-list maximum.
- **VRR** is declared two ways and either one counts: an AMD FreeSync
  vendor-specific data block in the CTA-861 extension (OUI 00-00-1A), or the
  EDID's own continuous-frequency feature bit together with a Monitor Range
  Limits descriptor whose vertical window is wide enough to be a VRR range —
  a fixed-rate panel also ships a range descriptor, but a legacy one spans a
  few hertz where a VRR window spans tens.
- **Unreadable is unknown.** A missing, truncated or checksum-failing EDID
  yields ``None``, never a guess in either direction — the caller decides what
  unknown means for it (discovery registers nothing, the UI says "unknown").
"""

from __future__ import annotations

from dataclasses import dataclass

_HEADER = bytes.fromhex("00ffffffffffff00")

# A fixed-rate panel's range descriptor spans a few hertz (56-76 on a classic
# 60-75 Hz panel); an Adaptive-Sync window spans tens (48-144, 48-300). The
# threshold sits between the two populations, and the continuous-frequency bit
# must agree before the range alone is believed.
_VRR_MIN_SPAN_HZ = 10

_AMD_OUI = bytes((0x1A, 0x00, 0x00))  # 00-00-1A little-endian, AMD's FreeSync block


@dataclass(frozen=True)
class EdidInfo:
    """What one panel's EDID declares. Fields are None where it was silent."""

    native_width: int | None
    native_height: int | None
    native_refresh_hz: int | None
    supports_vrr: bool
    vrr_min_hz: int | None
    vrr_max_hz: int | None


def _preferred_timing(block: bytes) -> tuple[int | None, int | None, int | None]:
    """Width, height and refresh from the preferred DTD at offset 54."""
    d = block[54:72]
    pixel_clock_10khz = int.from_bytes(d[0:2], "little")
    if pixel_clock_10khz == 0:  # a display descriptor, not a timing
        return None, None, None
    h_active = d[2] + ((d[4] >> 4) << 8)
    h_blank = d[3] + ((d[4] & 0x0F) << 8)
    v_active = d[5] + ((d[7] >> 4) << 8)
    v_blank = d[6] + ((d[7] & 0x0F) << 8)
    total = (h_active + h_blank) * (v_active + v_blank)
    if not total:
        return None, None, None
    refresh = round(pixel_clock_10khz * 10_000 / total)
    return h_active or None, v_active or None, refresh or None


def _range_limits(block: bytes) -> tuple[int | None, int | None]:
    """Vertical min/max from the Monitor Range Limits descriptor (tag 0xFD)."""
    for offset in (54, 72, 90, 108):
        d = block[offset : offset + 18]
        if d[0:2] != b"\x00\x00" or d[3] != 0xFD:
            continue
        v_min, v_max = d[5], d[6]
        offsets = d[4]
        if offsets & 0b01:  # vertical max is offset by 255
            v_max += 255
        if (offsets & 0b11) == 0b11:  # and so is vertical min
            v_min += 255
        return v_min, v_max
    return None, None


def _has_freesync_block(raw: bytes) -> bool:
    """AMD's vendor-specific data block in the CTA-861 extension."""
    if len(raw) < 256 or raw[126] == 0 or raw[128] != 0x02:
        return False
    cta = raw[128:256]
    dtd_start = cta[2]
    if dtd_start < 4:
        dtd_start = len(cta)
    index = 4
    while index < dtd_start:
        tag = cta[index] >> 5
        length = cta[index] & 0x1F
        if tag == 0x03 and length >= 3 and cta[index + 1 : index + 4] == _AMD_OUI:
            return True
        index += 1 + length
    return False


def parse_edid(raw: bytes) -> EdidInfo | None:
    """Parse a panel's EDID, or return None when it cannot be believed.

    Returns:
        The panel's own declarations, or None for a missing, truncated or
        checksum-failing block — unreadable is unknown, never a guess.
    """
    try:
        if len(raw) < 128 or raw[:8] != _HEADER or sum(raw[:128]) % 256 != 0:
            return None
        width, height, refresh = _preferred_timing(raw)
        v_min, v_max = _range_limits(raw)
        continuous = bool(raw[24] & 0x01)
        wide_window = v_min is not None and v_max is not None and v_max - v_min >= _VRR_MIN_SPAN_HZ
        supports_vrr = _has_freesync_block(raw) or (continuous and wide_window)
        return EdidInfo(
            native_width=width,
            native_height=height,
            native_refresh_hz=refresh,
            supports_vrr=supports_vrr,
            vrr_min_hz=v_min if supports_vrr else None,
            vrr_max_hz=v_max if supports_vrr else None,
        )
    except Exception:
        return None
