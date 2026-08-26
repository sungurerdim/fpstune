"""The monitor hot-plug poller must start at the documented rate and stop on exit.

Two failures this pins, both of which shipped:

1. The call site passed ``interval=60.0`` while C7's cache table and the
   lifespan's own comment two lines above it both said 15 s. A companion test
   (``test_hardware_manager.py``) pins the constant; nothing pinned the caller,
   so the two could disagree indefinitely — and did.
2. ``stop_hotplug_polling`` existed and was never called. The thread re-detected
   monitors — one PowerShell process each time — for as long as the process
   lived, including after shutdown had been requested and while the UI was
   closed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fpstune.api.main import lifespan


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_the_hotplug_poller() -> None:
    hw_mgr = MagicMock()

    with (
        patch("fpstune.utils.hardware_manager.hardware_manager", hw_mgr),
        patch("fpstune.api.main.start_gpu_detection_async"),
        patch("fpstune.api.main.threading.Thread"),
        patch("fpstune.benchmark.headroom_watch.start_headroom_watch"),
        patch("fpstune.benchmark.headroom_watch.stop_headroom_watch"),
        patch("fpstune.api.main.stop_background_refresh"),
        patch("fpstune.utils.detect.is_gpu_detecting", return_value=False),
    ):
        async with lifespan(MagicMock()):
            hw_mgr.start_hotplug_polling.assert_called_once_with()
            hw_mgr.stop_hotplug_polling.assert_not_called()

        hw_mgr.stop_hotplug_polling.assert_called_once()


def test_the_call_site_names_no_interval_of_its_own() -> None:
    """An explicit interval at the call site is how the 60 s disagreement got in.

    The poller's default is the named constant; passing anything here re-opens
    the gap between what CLAUDE.md documents and what runs.
    """
    import inspect

    from fpstune.api import main

    source = inspect.getsource(main.lifespan)
    assert "start_hotplug_polling()" in source
    assert "start_hotplug_polling(interval" not in source
