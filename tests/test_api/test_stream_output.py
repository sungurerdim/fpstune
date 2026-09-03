"""A streamed run says what it is doing, and says it only where it measured it.

The bulk stream used to report three moments — started, applied, verified — and
nothing in between, so a thirty-minute repair was one spinner. These tests pin
the two halves of the fix: the command and its output reach the client while it
runs, and a percentage appears only for a command that prints one.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import pytest

from fpstune.api.routes import settings_stream
from fpstune.settings.base import (
    PERCENT_PROGRESS,
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)


def _action(setting_id: str, *, progress: bool) -> SettingExecutor:
    """A cleanup action, with or without a command that reports its own progress."""
    return SettingExecutor(
        id=setting_id,
        category=SettingCategory.MAINTENANCE,
        display_name="Windows Image Repair",
        description="Repairs the Windows component store. Damage there fails updates.",
        value_type=SettingValueType.BOOL,
        choices=(),
        default_value=False,
        recommended_value=True,
        is_action=True,
        current_impact="Current: Windows image health unknown",
        recommended_impact="Scan: Repairs the image → improved stability",
        scope=SettingScope.COMPLETE,
        effect="Repairs the Windows image",
        impact_scores={"stability": "improved", "disk_freed": "0-2GB"},
        detect_type=DetectType.POWERSHELL,
        detect_command="maintenance_status",
        apply_type=DetectType.POWERSHELL,
        apply_command="dism_health",
        duration_estimate="10-30 min",
        progress_pattern=PERCENT_PROGRESS if progress else None,
    )


class TestPercent:
    """What counts as a progress report, and what does not."""

    def test_a_bar_reports_its_percentage(self) -> None:
        """DISM draws its own bar; the number in it is the progress."""
        assert settings_stream._percent(PERCENT_PROGRESS, "[====   42.0%    ]") == 42.0

    def test_the_sign_may_come_first(self) -> None:
        """The sign moves with the display language; the number does not."""
        assert settings_stream._percent(PERCENT_PROGRESS, "Dogrulama %42 tamamlandi") == 42.0

    def test_the_sign_may_come_last(self) -> None:
        """This machine's sfc.exe.mui: "Verification %1!u!%% complete." """
        assert settings_stream._percent(PERCENT_PROGRESS, "Verification 42% complete.") == 42.0

    def test_a_command_that_declares_no_pattern_reports_no_progress(self) -> None:
        """A delete script printing a path with a percent sign is not progress."""
        assert settings_stream._percent(None, "Removing C:\\cache\\100% off\\a.tmp") is None

    def test_a_percentage_is_held_inside_its_range(self) -> None:
        assert settings_stream._percent(PERCENT_PROGRESS, "999% done") == 100.0


class TestOutputPump:
    """The bridge from the reader thread to the event stream."""

    async def _drain(self, setting: SettingExecutor, lines: list[tuple[str, bool]]) -> list[Any]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        pump = settings_stream._output_pump(setting, queue, loop)

        # Off the event loop thread, the way the PowerShell reader calls it.
        await asyncio.to_thread(lambda: [pump(text, replaces) for text, replaces in lines])
        await asyncio.sleep(0)  # let call_soon_threadsafe land

        events = []
        while not queue.empty():
            raw = queue.get_nowait()
            assert raw is not None
            events.append(json.loads(raw.removeprefix("data: ").strip()))
        return events

    @pytest.mark.asyncio
    async def test_every_line_reaches_the_stream_with_its_redraw_flag(self) -> None:
        events = await self._drain(
            _action("maintenance:dism_health", progress=True),
            [("[=   10.0% ]", True), ("[==  20.0% ]", True), ("Done.", False)],
        )

        assert [e["text"] for e in events] == ["[=   10.0% ]", "[==  20.0% ]", "Done."]
        assert [e["replaces"] for e in events] == [True, True, False]
        assert all(e["event"] == "output" for e in events)

    @pytest.mark.asyncio
    async def test_progress_rides_along_only_where_the_command_reports_it(self) -> None:
        with_bar = await self._drain(
            _action("maintenance:dism_health", progress=True), [("[=   10.0% ]", True)]
        )
        without = await self._drain(
            _action("cleanup:npm_cache", progress=False), [("[=   10.0% ]", True)]
        )

        assert with_bar[0]["percent"] == 10.0
        assert "percent" not in without[0], (
            "a command that declares no progress pattern must not produce a bar"
        )


class TestSettingsCarryTheirOwnProgress:
    """The three long actions this ships, against their own definitions."""

    def test_the_long_actions_declare_a_duration_and_a_pattern(self) -> None:
        from fpstune.settings.definitions.system import (
            CLEANUP_DISM,
            MAINTENANCE_DISM_HEALTH,
            MAINTENANCE_SFC,
        )

        for setting in (CLEANUP_DISM, MAINTENANCE_DISM_HEALTH, MAINTENANCE_SFC):
            assert setting.duration_estimate, f"{setting.id} runs for minutes and says nothing"
            assert setting.progress_pattern, f"{setting.id} prints a percentage nobody reads"

    def test_the_shipped_pattern_is_a_valid_regex(self) -> None:
        # A definition shipping a broken pattern would silently disable progress
        # for that setting rather than fail anywhere visible.
        assert re.compile(PERCENT_PROGRESS)
