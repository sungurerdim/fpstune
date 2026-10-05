"""Reset writes a launcher's own default, never a value it never shipped with.

Steam ships with downloads during gameplay off and no download cap. Both rows
declared the opposite as stock, so "reset" turned mid-match downloads on and
wrote a 10 MB/s cap into config.vdf.
"""

from __future__ import annotations

from fpstune.settings.definitions.launchers import (
    STEAM_DOWNLOAD_THROTTLE,
    STEAM_DOWNLOADS_DURING_GAMEPLAY,
)


def test_downloads_during_gameplay_stock_is_off() -> None:
    assert STEAM_DOWNLOADS_DURING_GAMEPLAY.default_value == "disabled"
    # An absent key is Steam's default, so it must read as off.
    assert STEAM_DOWNLOADS_DURING_GAMEPLAY.detect_args["absent"] == "disabled"


def test_download_throttle_stock_is_no_cap() -> None:
    assert STEAM_DOWNLOAD_THROTTLE.default_value == "unlimited"
    assert STEAM_DOWNLOAD_THROTTLE.recommended_value == "unlimited"
