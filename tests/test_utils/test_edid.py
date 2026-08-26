"""What parse_edid believes, and what it refuses to guess.

The defects this file exists for, both shipped: ``supports_vrr`` was the guess
``maxHz > 60`` — which switched driver V-Sync and a frame cap on for a plain
75 Hz office panel and told a 60 Hz FreeSync panel it had nothing — and the
native refresh rate was a copy of the mode-list maximum, so three comments
reasoning about the two fields' difference described a difference that could
never exist.
"""

from __future__ import annotations

from fpstune.utils.edid import parse_edid
from tests.test_utils.edid_builder import build_edid


def _previous_guess(max_hz: int) -> bool:
    """The rule as it shipped (detect.py: ``$maxHz -gt 60``), kept verbatim."""
    return max_hz > 60


class TestVrrIsTheEdidsAnswer:
    def test_a_plain_75hz_panel_is_not_vrr(self) -> None:
        """The gate's first fixture — and the previous guess got it wrong."""
        office = build_edid(refresh=75, v_range=(56, 76))
        info = parse_edid(office)
        assert info is not None
        assert info.supports_vrr is False
        assert _previous_guess(75) is True  # what shipped: V-Sync ON, 72 fps cap

    def test_a_60hz_freesync_panel_is_vrr(self) -> None:
        """The mirror case: the guess told this panel it had nothing."""
        freesync = build_edid(refresh=60, freesync_block=True)
        info = parse_edid(freesync)
        assert info is not None
        assert info.supports_vrr is True
        assert _previous_guess(60) is False

    def test_a_continuous_panel_with_a_wide_window_is_vrr(self) -> None:
        gaming = build_edid(refresh=144, continuous_frequency=True, v_range=(48, 144))
        info = parse_edid(gaming)
        assert info is not None
        assert info.supports_vrr is True
        assert (info.vrr_min_hz, info.vrr_max_hz) == (48, 144)

    def test_a_legacy_range_alone_is_not_a_vrr_window(self) -> None:
        """Fixed-rate panels ship 56-61 style ranges; spread alone cannot decide."""
        narrow = build_edid(refresh=60, continuous_frequency=True, v_range=(56, 61))
        no_continuous = build_edid(refresh=144, v_range=(48, 144))
        for edid in (narrow, no_continuous):
            info = parse_edid(edid)
            assert info is not None
            assert info.supports_vrr is False


class TestNativeRefreshIsTheDtdsAnswer:
    def test_the_preferred_timing_rate_is_read_not_derived(self) -> None:
        info = parse_edid(build_edid(width=2560, height=1440, refresh=144))
        assert info is not None
        assert info.native_refresh_hz == 144
        assert (info.native_width, info.native_height) == (2560, 1440)


class TestUnreadableIsUnknown:
    def test_garbage_yields_none(self) -> None:
        assert parse_edid(b"\x00" * 128) is None

    def test_truncated_yields_none(self) -> None:
        assert parse_edid(build_edid()[:64]) is None

    def test_a_failing_checksum_yields_none(self) -> None:
        """A block that cannot vouch for itself proves nothing about the panel."""
        corrupted = bytearray(build_edid(refresh=144, freesync_block=True))
        corrupted[30] ^= 0xFF
        assert parse_edid(bytes(corrupted)) is None
