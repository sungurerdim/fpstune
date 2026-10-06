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
from collections.abc import Iterator
from pathlib import Path

import pytest
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


# ---------------------------------------------------------------------------
# Class-wide guards. The tests above pin the two reported lines; these pin the
# *class*: whatever a message carries and whoever logs it, the file is plain
# text, and an activity is written once to each sink.
#
# They go through the real thing — `setup_logging` with a real temp file and the
# real shared `console` with its output captured — and touch only the public
# surface (`setup_logging`, `log_activity`, `activity_log`, `console`), so the
# same file runs unchanged against the tree as it was before either fix.
# ---------------------------------------------------------------------------


_Wired = tuple[logging.Logger, Path]


@pytest.fixture
def wired_logger(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[_Wired]:
    """The product's own logger wiring over a temp file; the shared state is restored.

    ``request.param`` (optional) is whether the console formatter emits colour —
    the terminal case, where escapes are in the line before Rich parses them.
    """
    from fpstune.utils import logger as logger_module

    use_colors = bool(getattr(request, "param", False))
    logger = logging.getLogger(logger_module.LOGGER_NAME)
    saved = (list(logger.handlers), logger.level, logger.propagate, logger.disabled)
    # The sources are loggers of their own, and another test in the same process
    # leaves them configured: `api.main._get_logger` pins `fpstune.api` to WARNING
    # with a stdout handler of its own the first time a route test imports it, so
    # a debug/info record from that source never reached the file (13 of 15
    # lines, only when a worker ran a route test first). Each source starts from
    # "inherit everything from `fpstune`" and is put back as it was found.
    children = {
        name: (list(child.handlers), child.level, child.propagate, child.disabled)
        for name in _SOURCES
        if (child := logging.getLogger(name)) is not logger
    }
    for name in children:
        child = logging.getLogger(name)
        child.handlers = []
        child.setLevel(logging.NOTSET)
        child.propagate = True
        child.disabled = False
    previous_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    logger.disabled = False
    original = logger_module._should_use_colors
    logger_module._should_use_colors = lambda: use_colors
    log_file = tmp_path / "fpstune.log"
    try:
        logger_module.setup_logging(level=logging.DEBUG, log_file=log_file)
        yield logger, log_file
    finally:
        logger_module._should_use_colors = original
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        for handler in saved[0]:
            logger.addHandler(handler)
        logger.setLevel(saved[1])
        logger.propagate = saved[2]
        logger.disabled = saved[3]
        for name, (handlers, level, propagate, disabled) in children.items():
            child = logging.getLogger(name)
            child.handlers = handlers
            child.setLevel(level)
            child.propagate = propagate
            child.disabled = disabled
        logging.disable(previous_disable)


def _file_text(logger: logging.Logger, log_file: Path) -> str:
    for handler in logger.handlers:
        handler.flush()
    return log_file.read_text(encoding="utf-8")


# Every shape of terminal control a message can carry in from outside: our own
# palette, a child process's cursor moves and erases (PowerShell progress), an
# OSC title or hyperlink, a private-mode toggle, an 8-bit CSI, a bare ESC, and
# Rich markup (which is plain text to a file and must stay so).
_PAYLOADS = {
    "palette": f"{_Colors.BOLD}{_Colors.BRIGHT_RED}[FAIL]{_Colors.RESET} APPLY ERROR x",
    "sgr-256": "\x1b[38;5;208mwarm\x1b[0m",
    "sgr-truecolor": "\x1b[38;2;10;20;30mtrue\x1b[0m",
    "erase-line": "progress 40%\x1b[2K\x1b[1Gprogress 100%",
    "cursor-hide": "\x1b[?25lworking\x1b[?25h",
    "osc-title": "\x1b]0;PowerShell\x07window",
    "osc-hyperlink": "\x1b]8;;https://example.com\x1b\\link text\x1b]8;;\x1b\\",
    "c1-csi": "\x9b31mred\x9b0m",
    "bare-esc": "tail\x1b",
    "rich-markup": "[bold red]not markup[/bold red] [link=https://example.com]x[/link]",
}
# The words a reader must still find once the escapes are gone.
_READABLE = {
    "palette": "[FAIL] APPLY ERROR x",
    "sgr-256": "warm",
    "sgr-truecolor": "true",
    "erase-line": "progress 40%",
    "cursor-hide": "working",
    "osc-title": "window",
    "osc-hyperlink": "link text",
    "c1-csi": "red",
    "bare-esc": "tail",
    "rich-markup": "[bold red]not markup[/bold red]",
}
_LEVELS = (
    ("debug", logging.DEBUG),
    ("info", logging.INFO),
    ("warning", logging.WARNING),
    ("error", logging.ERROR),
    ("critical", logging.CRITICAL),
)
_SOURCES = ("fpstune", "fpstune.api", "fpstune.settings.executors.registry")


class TestLogFileNeverHoldsAnEscape:
    """Class guard 1: no level, no source, no payload puts an escape in the file."""

    @pytest.mark.parametrize("wired_logger", [False, True], indirect=True, ids=["plain", "colour"])
    @pytest.mark.parametrize("key", list(_PAYLOADS))
    def test_every_level_from_every_source(self, wired_logger: _Wired, key: str) -> None:
        logger, log_file = wired_logger
        for source in _SOURCES:
            for name, level in _LEVELS:
                logging.getLogger(source).log(level, "%s %s", name, _PAYLOADS[key])

        content = _file_text(logger, log_file)

        assert "\x1b" not in content, "an escape sequence reached the log file"
        assert "\x9b" not in content, "an 8-bit CSI reached the log file"
        assert content.count(_READABLE[key]) == len(_SOURCES) * len(_LEVELS), (
            "stripping ate the message text itself"
        )

    @pytest.mark.parametrize("wired_logger", [True], indirect=True)
    def test_an_escape_inside_a_traceback_is_stripped_too(self, wired_logger: _Wired) -> None:
        """`exc_info` is formatted by the same formatter; its text is message-controlled."""
        logger, log_file = wired_logger
        try:
            raise RuntimeError("\x1b[31mpowershell said no\x1b[0m")
        except RuntimeError:
            logger.exception("apply failed")

        content = _file_text(logger, log_file)

        assert "\x1b" not in content
        assert "RuntimeError: powershell said no" in content

    @pytest.mark.parametrize("wired_logger", [True], indirect=True)
    @pytest.mark.parametrize("level", ["info", "success", "warning", "error", "bogus"])
    def test_activities_with_escapes_in_the_message(self, wired_logger: _Wired, level: str) -> None:
        from fpstune.utils.logger import log_activity

        logger, log_file = wired_logger
        log_activity(f"{tweak_label('system:hyper_v')} \x1b[2Kdone\x1b[0m", level)

        content = _file_text(logger, log_file)

        assert "\x1b" not in content
        assert "system:hyper_v" in content
        assert "done" in content


@pytest.fixture
def debug_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """`utils/debug.py` writing for real, into a temp directory, with FPSTUNE_DEBUG set."""
    from fpstune.utils import debug as debug_module

    monkeypatch.setattr(debug_module, "DEBUG_ENABLED", True)
    monkeypatch.setattr(debug_module, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(debug_module, "_log_writers", {})
    try:
        yield tmp_path
    finally:
        for writer in list(debug_module._log_writers.values()):
            for handler in list(writer.handlers):
                handler.close()
                writer.removeHandler(handler)


class TestDebugFilesNeverHoldAnEscape:
    """Class guard 3: ``debug.log`` and its component files are plain text too.

    ``utils/debug.py`` wrote its four files through a bare ``Formatter``, so a
    PowerShell command or a detection line carrying a cursor move or an OSC title
    reached ``powershell.log`` / ``hardware.log`` / ``debug.log`` verbatim — the
    same noise 330fdd5 removed from ``fpstune.log``, left standing beside it.
    """

    @pytest.mark.parametrize("component", ["powershell", "hardware", "settings", "unmapped"])
    @pytest.mark.parametrize("key", list(_PAYLOADS))
    def test_every_component_file_and_the_json_log(
        self, debug_log_dir: Path, component: str, key: str
    ) -> None:
        from fpstune.utils.debug import debug_log

        debug_log(component, f"entry {_PAYLOADS[key]}", {"k": "v"})

        written = [p for p in debug_log_dir.glob("*.log") if p.stat().st_size]
        assert written, "nothing was written, so the guard below proves nothing"
        for path in written:
            content = path.read_text(encoding="utf-8")
            assert "\x1b" not in content, f"an escape sequence reached {path.name}"
            assert "\x9b" not in content, f"an 8-bit CSI reached {path.name}"
            assert "\\u001b" not in content, f"{path.name} holds an escape as JSON text"
            assert _READABLE[key] in content, f"stripping ate the message text in {path.name}"


class TestEveryActivityIsWrittenOnce:
    """Class guard 2: one activity → one terminal line and one file line.

    Only ``log_activity`` used to forward, so direct writers to the store showed
    in the app and nowhere else (zero); the fix must not turn into a second
    forwarder at some other layer (two). Counting both sinks, through both entry
    points, catches either direction.
    """

    @pytest.mark.parametrize("wired_logger", [False, True], indirect=True, ids=["plain", "colour"])
    @pytest.mark.parametrize("level", ["info", "success", "warning", "error", "bogus"])
    @pytest.mark.parametrize("entry", ["log_activity", "store_add"])
    def test_one_terminal_line_and_one_file_line(
        self, wired_logger: _Wired, level: str, entry: str
    ) -> None:
        from fpstune.utils.console import console
        from fpstune.utils.logger import activity_log, log_activity

        logger, log_file = wired_logger
        marker = f"marker-{entry}-{level}-7f3a"
        with console.capture() as capture:
            if entry == "log_activity":
                log_activity(marker, level)
            else:
                activity_log.add(marker, level)

        terminal = capture.get()
        content = _file_text(logger, log_file)

        assert terminal.count(marker) == 1, f"terminal saw it {terminal.count(marker)} times"
        assert content.count(marker) == 1, f"log file has it {content.count(marker)} times"

    @pytest.mark.parametrize("wired_logger", [False], indirect=True)
    def test_calling_setup_logging_twice_does_not_double_the_sinks(
        self, wired_logger: _Wired, tmp_path: Path
    ) -> None:
        """A second `setup_logging` (a re-init, a `--verbose` restart) must replace handlers, not stack them."""
        from fpstune.utils.console import console
        from fpstune.utils.logger import log_activity, setup_logging

        logger, _ = wired_logger
        second = tmp_path / "second.log"
        setup_logging(level=logging.DEBUG, log_file=second)
        marker = "marker-reinit-91bc"
        with console.capture() as capture:
            log_activity(marker, "success")

        assert capture.get().count(marker) == 1
        assert _file_text(logger, second).count(marker) == 1
        assert len(logger.handlers) == 2
