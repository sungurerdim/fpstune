"""Synthetic EDID blocks for tests — built, not captured.

A captured EDID would be a real panel's identity in the tree (C9); a built one
carries exactly the declarations a test needs and nothing else. The builder
writes a valid 128-byte base block (header, version 1.4, preferred DTD,
checksum) and optionally a CTA-861 extension carrying AMD's FreeSync
vendor-specific data block.
"""

from __future__ import annotations

_HEADER = bytes.fromhex("00ffffffffffff00")
_DUMMY_DESCRIPTOR = bytes([0x00, 0x00, 0x00, 0x10] + [0x00] * 14)

# Modest blanking keeps the 16-bit pixel-clock field in range at high refresh.
_H_BLANK = 80
_V_BLANK = 30


def _dtd(width: int, height: int, refresh: int) -> bytes:
    total = (width + _H_BLANK) * (height + _V_BLANK)
    pclk_10khz = round(refresh * total / 10_000)
    if pclk_10khz > 0xFFFF:
        raise ValueError(f"{width}x{height}@{refresh} overflows the DTD pixel clock")
    d = bytearray(18)
    d[0:2] = pclk_10khz.to_bytes(2, "little")
    d[2] = width & 0xFF
    d[3] = _H_BLANK & 0xFF
    d[4] = ((width >> 8) << 4) | (_H_BLANK >> 8)
    d[5] = height & 0xFF
    d[6] = _V_BLANK & 0xFF
    d[7] = ((height >> 8) << 4) | (_V_BLANK >> 8)
    return bytes(d)


def _range_limits(v_min: int, v_max: int) -> bytes:
    d = bytearray(18)
    d[3] = 0xFD
    d[5] = v_min
    d[6] = v_max
    d[7] = 0x1E  # horizontal min, irrelevant to the parser
    d[8] = 0x50  # horizontal max, irrelevant to the parser
    return bytes(d)


def build_edid(
    *,
    width: int = 1920,
    height: int = 1080,
    refresh: int = 60,
    continuous_frequency: bool = False,
    v_range: tuple[int, int] | None = None,
    freesync_block: bool = False,
) -> bytes:
    """A valid EDID declaring exactly what the arguments say."""
    block = bytearray(128)
    block[0:8] = _HEADER
    block[8:10] = b"\x04\x21"  # a nonzero PNP id
    block[18] = 1  # EDID version
    block[19] = 4  # EDID revision
    block[20] = 0x80  # digital input
    block[24] = 0x01 if continuous_frequency else 0x00
    block[54:72] = _dtd(width, height, refresh)
    block[72:90] = _range_limits(*v_range) if v_range else _DUMMY_DESCRIPTOR
    block[90:108] = _DUMMY_DESCRIPTOR
    block[108:126] = _DUMMY_DESCRIPTOR
    block[126] = 1 if freesync_block else 0
    block[127] = (256 - sum(block[:127])) % 256
    if not freesync_block:
        return bytes(block)

    ext = bytearray(128)
    ext[0] = 0x02  # CTA-861
    ext[1] = 0x03
    vendor = bytes([(0x03 << 5) | 5, 0x1A, 0x00, 0x00, 0x01, 0x00])  # OUI 00-00-1A
    ext[4 : 4 + len(vendor)] = vendor
    ext[2] = 4 + len(vendor)  # DTDs would start here
    ext[127] = (256 - sum(ext[:127])) % 256
    return bytes(block) + bytes(ext)
