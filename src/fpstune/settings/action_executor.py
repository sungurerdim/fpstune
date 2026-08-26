"""Action executor with SSE streaming for maintenance tasks.

Provides live console output for long-running maintenance operations
like DISM cleanup, SFC scan, disk optimization, etc.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess
import sys
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.utils.powershell import substitute_placeholders

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor


@dataclass
class ActionEvent:
    """SSE event data for action execution."""

    type: str  # "output", "progress", "complete", "error"
    line: str = ""
    progress: int = 0
    success: bool = False
    error: str = ""

    def to_json(self) -> str:
        """Convert to JSON string for SSE."""
        return json.dumps(
            {
                "type": self.type,
                "line": self.line,
                "progress": self.progress,
                "success": self.success,
                "error": self.error,
            }
        )


class ActionExecutor:
    """Executes maintenance actions with streaming output."""

    MAX_OUTPUT_LINES = 100  # Keep last N lines in memory

    # These actions are DISM and SFC class: half an hour is a slow-disk run,
    # not a hang. Anything past this is a stuck process, and a stuck DISM left
    # running touches the component store for as long as it lives.
    MAX_RUNTIME_SECONDS = 3600.0

    def __init__(self, setting: SettingExecutor) -> None:
        """Initialize executor for a specific action setting.

        Args:
            setting: The action setting to execute.
        """
        self.setting = setting
        self._output_lines: list[str] = []
        self._process: asyncio.subprocess.Process | None = None

    async def execute_streaming(self) -> AsyncGenerator[str, None]:
        """Execute the action and yield SSE events.

        Yields:
            JSON-encoded ActionEvent strings for SSE.
        """
        if not self.setting.is_action:
            yield ActionEvent(type="error", error="Not an action setting").to_json()
            return

        yield ActionEvent(type="output", line=f"Starting {self.setting.display_name}...").to_json()

        try:
            # Build command based on action type
            try:
                command = self._build_command()
            except ValueError as exc:
                # The escaping layer refused a value it could not place safely.
                # Distinguished from every other failure here because it is a
                # refusal, not a crash: nothing ran, so nothing needs undoing.
                yield ActionEvent(
                    type="error", error=f"PowerShell command rejected: {exc}"
                ).to_json()
                return
            if not command:
                yield ActionEvent(
                    type="error", error="No command configured for this action"
                ).to_json()
                return

            # Execute with streaming. Closed explicitly rather than left to
            # garbage collection: when the client disconnects, this generator
            # is closed at its yield, and the inner one must be closed with it
            # so its cleanup (killing the subprocess) runs now, not at GC time.
            stream = self._run_command_streaming(command)
            try:
                async for event in stream:
                    yield event.to_json()
            finally:
                await stream.aclose()

        except Exception as e:
            yield ActionEvent(type="error", error=str(e)).to_json()

    def _build_command(self) -> list[str] | None:
        """Build command list for subprocess execution."""
        # PowerShell actions
        if self.setting.apply_type.value == "powershell":
            cmd_key = self.setting.apply_command.strip()
            if not cmd_key:
                return None

            # Resolve action command key to actual script
            if cmd_key in ACTION_COMMANDS:
                cmd = ACTION_COMMANDS[cmd_key]
            else:
                cmd = self.setting.apply_command

            # Substitute %placeholders% for PowerShell compatibility
            if self.setting.apply_args:
                cmd = substitute_placeholders(cmd, **self.setting.apply_args)

            return ["powershell", "-NoProfile", "-Command", cmd]

        # Registry actions typically don't have streaming output
        # but we can still execute them
        if self.setting.apply_type.value == "registry":
            return None  # Registry actions are instant, no streaming needed

        return None

    async def _run_command_streaming(self, command: list[str]) -> AsyncGenerator[ActionEvent, None]:
        """Run command and stream output line by line.

        Args:
            command: Command to execute as list.

        Yields:
            ActionEvent for each output line.
        """
        if sys.platform != "win32":
            # For non-Windows, just simulate
            yield ActionEvent(type="output", line="[Simulated] Command would run on Windows")
            await asyncio.sleep(0.5)
            yield ActionEvent(type="complete", success=True)
            return

        process: asyncio.subprocess.Process | None = None
        try:
            # Start process with pipes
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self._process = process

            # One deadline over the whole run. Reads are bounded by what is
            # left of it, so a process that goes quiet cannot hold this
            # generator — and the PowerShell behind it — open forever.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.MAX_RUNTIME_SECONDS
            timed_out = False

            line_count = 0
            if process.stdout:
                while True:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        timed_out = True
                        break
                    try:
                        line_bytes = await asyncio.wait_for(process.stdout.readline(), remaining)
                    except TimeoutError:
                        timed_out = True
                        break
                    if not line_bytes:
                        break

                    line = line_bytes.decode("utf-8", errors="replace").rstrip()
                    if line:
                        self._output_lines.append(line)
                        # Keep only last N lines
                        if len(self._output_lines) > self.MAX_OUTPUT_LINES:
                            self._output_lines.pop(0)

                        line_count += 1
                        yield ActionEvent(type="output", line=line)

                        # Small delay to prevent flooding
                        if line_count % 10 == 0:
                            await asyncio.sleep(0.01)

            return_code: int | None = None
            if not timed_out:
                try:
                    return_code = await asyncio.wait_for(
                        process.wait(), max(deadline - loop.time(), 0.0)
                    )
                except TimeoutError:
                    timed_out = True

            if timed_out or return_code is None:
                yield ActionEvent(
                    type="error",
                    error=(f"Action exceeded {int(self.MAX_RUNTIME_SECONDS)}s and was terminated"),
                )
                return

            if return_code == 0:
                yield ActionEvent(type="complete", success=True)
            else:
                yield ActionEvent(
                    type="complete",
                    success=False,
                    error=f"Process exited with code {return_code}",
                )

        except Exception as e:
            yield ActionEvent(type="error", error=str(e))
        finally:
            # Runs on normal exit, on timeout, on cancellation, and when the
            # consumer closes the generator (client disconnect). Whatever the
            # path, the subprocess never outlives the stream: an orphaned DISM
            # or SFC keeps writing to the component store with nobody watching.
            if process is not None and process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                with contextlib.suppress(Exception):
                    await process.wait()


async def execute_action(setting: SettingExecutor) -> AsyncGenerator[str, None]:
    """Convenience function to execute an action with streaming.

    Args:
        setting: The action setting to execute.

    Yields:
        SSE-formatted event strings.
    """
    executor = ActionExecutor(setting)
    stream = executor.execute_streaming()
    try:
        async for event in stream:
            yield event
    finally:
        # Chain the close down: the route's generator being closed on client
        # disconnect must reach the subprocess cleanup immediately.
        await stream.aclose()
