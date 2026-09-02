"""Every operation and every outcome in a log line has a colour of its own.

The line the owner pasted on 2026-09-02 — ``[FAIL] APPLY ERROR
game_config:mw4:dof_weapon: [WinError 5] …`` — arrived in one grey, and asked
for colour: apply and verify distinguishable at a glance, failure unmistakable.
The palette lives in the console formatter, so call sites write plain words and
the log file stays plain; the relay in the dev launcher carries the colour from
the child process to the terminal that can render it.
"""

from __future__ import annotations

import logging

from rich.text import Text

from fpstune.commands import presentation as ui
from fpstune.utils import logger as logger_module
from fpstune.utils.console import console
from fpstune.utils.logger import (
    _ANSI_ESCAPE,
    _OPERATION_COLORS,
    _STATUS_COLORS,
    _ColorFormatter,
    _Colors,
    colorize_tokens,
    log_activity,
)


def _record(message: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord("fpstune.api", level, "", 0, message, None, None)


class TestThePalette:
    def test_each_operation_has_its_own_colour(self) -> None:
        colours = list(_OPERATION_COLORS.values())
        assert len(set(colours)) == len(colours), "two operations share a colour"

    def test_done_failed_and_warned_are_three_different_families(self) -> None:
        assert _STATUS_COLORS["OK"] == _STATUS_COLORS["APPLIED"] == _STATUS_COLORS["VERIFIED"]
        assert _STATUS_COLORS["FAIL"] == _STATUS_COLORS["ERROR"] == _STATUS_COLORS["TIMEOUT"]
        assert len({_STATUS_COLORS["OK"], _STATUS_COLORS["FAIL"], _STATUS_COLORS["WARN"]}) == 3
        assert _Colors.BRIGHT_RED in _STATUS_COLORS["FAIL"]
        assert _Colors.BOLD in _STATUS_COLORS["FAIL"], "a failure is bold as well as red"

    def test_no_operation_colour_is_also_an_outcome_colour(self) -> None:
        """Magenta means apply and never means failed."""
        assert not set(_OPERATION_COLORS.values()) & set(_STATUS_COLORS.values())


class TestColouringAMessage:
    def test_the_reported_line_gets_its_operation_and_its_outcome_coloured(self) -> None:
        message = "[FAIL] APPLY ERROR game_config:mw4:dof_weapon: file is held open"
        coloured = colorize_tokens(message)
        assert f"{_STATUS_COLORS['FAIL']}FAIL{_Colors.RESET}" in coloured
        assert f"{_OPERATION_COLORS['APPLY']}APPLY{_Colors.RESET}" in coloured
        assert f"{_STATUS_COLORS['ERROR']}ERROR{_Colors.RESET}" in coloured
        assert _ANSI_ESCAPE.sub("", coloured) == message, "colour adds nothing but colour"

    def test_a_setting_id_and_lower_case_words_are_never_touched(self) -> None:
        message = "detect ok for game_config:mw4:ok and C:\\Users\\x\\apply.cfg"
        assert colorize_tokens(message) == message

    def test_verify_and_apply_are_told_apart(self) -> None:
        coloured = colorize_tokens("VERIFY FAILED then APPLY OK")
        assert coloured.index(_OPERATION_COLORS["VERIFY"]) < coloured.index(
            _OPERATION_COLORS["APPLY"]
        )
        assert _OPERATION_COLORS["VERIFY"] != _OPERATION_COLORS["APPLY"]


class TestThroughTheFormatter:
    def test_the_console_line_carries_the_palette_and_rich_can_parse_it(self) -> None:
        rendered = _ColorFormatter(use_colors=True).format(_record("[OK] APPLY system:x applied"))
        assert _OPERATION_COLORS["APPLY"] in rendered
        assert _STATUS_COLORS["OK"] in rendered
        text = Text.from_ansi(rendered)
        assert "\x1b" not in text.plain
        assert text.plain.endswith("[OK] APPLY system:x applied")
        assert text.spans

    def test_colours_off_means_no_escapes_anywhere(self) -> None:
        rendered = _ColorFormatter(use_colors=False).format(_record("[FAIL] APPLY ERROR x"))
        assert "\x1b" not in rendered

    def test_log_activity_writes_a_plain_prefix_for_the_formatter_to_colour(
        self, monkeypatch
    ) -> None:
        """The escape used to be baked into the message; now the file never sees one.

        Isolated from the rest of the suite on purpose: the fpstune logger does not
        propagate (so caplog sees nothing), other tests leave its level raised, and
        `logging.disable` may be set globally. A private logger, handed to
        `log_activity` through `get_logger`, sees exactly what this test emits.
        """
        seen: list[str] = []

        class Collect(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                seen.append(record.getMessage())

        private = logging.getLogger("fpstune.test.palette")
        private.handlers = [Collect(level=logging.DEBUG)]
        private.propagate = False
        private.setLevel(logging.DEBUG)
        private.disabled = False
        monkeypatch.setattr(logger_module, "get_logger", lambda: private)
        previous_disable = logging.root.manager.disable
        logging.disable(logging.NOTSET)
        try:
            log_activity("applied", "success")
            log_activity("broke", "error")
        finally:
            logging.disable(previous_disable)
        assert "[OK] applied" in seen
        assert "[FAIL] broke" in seen
        assert all("\x1b" not in m for m in seen)


class TestTheRelay:
    def test_a_childs_coloured_line_arrives_tagged_and_readable(self) -> None:
        line = f"INFO  | api | {_OPERATION_COLORS['APPLY']}APPLY{_Colors.RESET} done"
        with console.capture() as capture:
            ui.relay("API", line)
        shown = capture.get()
        assert "[API] " in shown
        assert "APPLY done" in _ANSI_ESCAPE.sub("", shown)
        assert "\x1b[" not in _ANSI_ESCAPE.sub("", shown), (
            "escapes are rendered or dropped, never shown"
        )

    def test_the_child_is_asked_for_colour_only_when_there_is_a_terminal(self) -> None:
        """`FORCE_COLOR` reaches the child through the env the launcher builds."""
        import inspect

        from fpstune import cli

        source = inspect.getsource(cli._serve_from_source)
        assert '"FORCE_COLOR": "1"' in source
        assert "ui.console.is_terminal" in source
        assert "_pump_output" in source, "the pipes must be drained, or the child blocks"

    def test_the_launcher_module_has_no_no_color_switch_left(self) -> None:
        from pathlib import Path

        root = Path(logger_module.__file__).resolve().parents[3]
        assert "NO_COLOR" not in (root / "start.bat").read_text(encoding="utf-8")
        ps1 = (root / "start.ps1").read_text(encoding="utf-8")
        assert "SupportsVirtualTerminal" in ps1
        assert 'FORCE_COLOR = "1"' in ps1
