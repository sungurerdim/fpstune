"""Colour reaches the terminal as colour, and never reaches the log file at all.

Both halves shipped broken, and the second one was hiding under the first.

**Terminal.** The formatter emits raw ANSI, and the handler handed that string
to Rich. But Rich on a legacy Windows console does not write ANSI — it sets
colour through the Win32 console API and emits plain text, so the escapes rode
through as literal characters and the user saw::

    ←[36mINFO ←[0m ←[2m|←[0m ←[35mapi   ←[0m ... fpstune API starting...

Measured on the machine that reported it: ``legacy_windows=True``,
``color_system='windows'``. The fix is to parse the escapes into Rich's own
spans so Rich knows what the colours are and can apply them by whichever
mechanism the terminal supports.

**File.** ``log_activity`` and ``tweak_label`` put escapes inside the *message*,
so the file handler wrote them into ``fpstune.log`` verbatim — noise in every
editor and every grep, on a stream that has no colour to render.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.text import Text

from fpstune.utils.logger import (
    _ANSI_ESCAPE,
    _ColorFormatter,
    _Colors,
    _PlainFileFormatter,
    setup_logging,
    tweak_label,
)


def _record(message: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord("fpstune.api", level, "", 0, message, None, None)


class TestTerminalOutput:
    """What Rich is handed, and what survives into the visible text."""

    def test_parsed_escapes_leave_no_literal_bytes_in_the_text(self) -> None:
        """The regression: `←[36m` in the rendered line is the whole reported bug."""
        rendered = _ColorFormatter(use_colors=True).format(_record("fpstune API starting..."))
        assert "\x1b[" in rendered, "precondition: the formatter still emits ANSI"

        text = Text.from_ansi(rendered)

        assert "\x1b" not in text.plain
        assert text.plain.startswith("INFO ")
        assert text.plain.endswith("fpstune API starting...")

    def test_the_colours_are_kept_rather_than_stripped(self) -> None:
        """Parsing must preserve the styling — stripping would fix the symptom and lose the colour."""
        rendered = _ColorFormatter(use_colors=True).format(_record("hello"))
        text = Text.from_ansi(rendered)

        assert text.spans, "from_ansi produced no styled spans, so the colour was lost"

    def test_colour_inside_the_message_is_parsed_too(self) -> None:
        """`log_activity` colours its own prefix, so the escapes are not only in the frame."""
        message = f"{_Colors.GREEN}[OK]{_Colors.RESET} applied"
        text = Text.from_ansi(_ColorFormatter(use_colors=True).format(_record(message)))

        assert "\x1b" not in text.plain
        assert "[OK] applied" in text.plain

    def test_square_brackets_in_a_message_stay_literal(self) -> None:
        """`from_ansi` never reads markup, which is what `markup=False` used to guard.

        A Windows path or a `[skipped]` must survive as itself.
        """
        text = Text.from_ansi(
            _ColorFormatter(use_colors=False).format(_record(r"[skipped] C:\Users\x\file.cfg"))
        )

        assert r"[skipped] C:\Users\x\file.cfg" in text.plain

    def test_colours_disabled_produces_no_escapes_at_all(self) -> None:
        rendered = _ColorFormatter(use_colors=False).format(_record("plain"))
        assert "\x1b" not in rendered


class TestLogFileOutput:
    """A file gets text, never escapes."""

    def test_message_colour_is_stripped_from_the_file_line(self) -> None:
        formatter = _PlainFileFormatter("%(levelname)-5s | %(name)-20s | %(message)s")
        message = f"{_Colors.GREEN}[OK]{_Colors.RESET} applied"

        line = formatter.format(_record(message))

        assert "\x1b" not in line
        assert "[OK] applied" in line

    def test_a_coloured_tweak_label_is_stripped_too(self) -> None:
        """`tweak_label` colours a setting id straight into the message."""
        formatter = _PlainFileFormatter("%(message)s")
        line = formatter.format(_record(f"applying {tweak_label('system:hyper_v')}"))

        assert "\x1b" not in line
        assert "system:hyper_v" in line

    def test_the_written_file_contains_no_escapes(self, tmp_path: Path) -> None:
        """End to end, through the handler the product actually installs."""
        log_file = tmp_path / "fpstune.log"
        logger = setup_logging(log_file=log_file)
        try:
            logger.info(f"{_Colors.RED}[FAIL]{_Colors.RESET} something went wrong")
            for handler in logger.handlers:
                handler.flush()

            content = log_file.read_text(encoding="utf-8")
            assert "\x1b" not in content
            assert "[FAIL] something went wrong" in content
        finally:
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)


class TestEscapePattern:
    """The pattern that does the stripping."""

    def test_matches_every_colour_code_this_module_emits(self) -> None:
        for code in (
            _Colors.RESET,
            _Colors.BOLD,
            _Colors.DIM,
            _Colors.RED,
            _Colors.GRAY,
            _Colors.BRIGHT_CYAN,
        ):
            assert _ANSI_ESCAPE.sub("", code) == "", f"{code!r} survived stripping"

    def test_leaves_ordinary_text_alone(self) -> None:
        """Bracketed text is not an escape; stripping must not eat a message."""
        text = r"[skipped] rate 786432 // 0 to 3"
        assert _ANSI_ESCAPE.sub("", text) == text
