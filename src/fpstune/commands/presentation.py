"""Everything fpstune shows in a terminal, in one place.

Two reasons this is its own module rather than scattered `console.print` calls.

**Alignment cannot be hand-typed.** The banner this replaced drew its own box
with `╔═╗║╚╝` and padded each line by eye. The wordmark inside it was one column
wider than the frame, so every release shipped a banner whose right edge did not
close. Rich measures what it renders; a frame it draws is a frame that fits, on
any width, forever. Nothing here counts characters.

**A terminal is not always a terminal.** Output gets piped into files, read over
SSH, pasted into issues, and run in a console whose code page predates Unicode.
So every glyph has an ASCII fallback and colour degrades on its own — a status
line has to still say what happened when it arrives as plain text.

The vocabulary is deliberately small: a heading, four status kinds, a key/value
block and a link. Anything a command needs beyond that is a sign the command is
trying to say too much at once.
"""

from __future__ import annotations

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fpstune import __version__
from fpstune.utils.console import console, content_width

__all__ = ["console"]

# Rich falls back to ASCII on a console that cannot encode box drawing, but it
# does not do that for arbitrary text, so the glyphs are chosen here. A legacy
# code page renders `✓` as a replacement character, and a status line whose
# marker is a black diamond is a status line nobody trusts.
_GLYPHS: dict[str, tuple[str, str, str]] = {
    # kind:       (unicode, ascii, style)
    "ok": ("✓", "+", "bold green"),
    "warn": ("!", "!", "bold yellow"),
    "fail": ("✗", "x", "bold red"),
    "step": ("›", ">", "bold cyan"),
    "info": ("·", "-", "dim"),
}


def _supports_unicode() -> bool:
    """Whether this console can encode the glyphs above."""
    encoding = getattr(console.file, "encoding", None) or "ascii"
    try:
        "✓›·".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _marker(kind: str) -> Text:
    unicode_glyph, ascii_glyph, style = _GLYPHS[kind]
    return Text(unicode_glyph if _supports_unicode() else ascii_glyph, style=style)


def status(kind: str, message: str, detail: str = "") -> None:
    """One outcome, one line: a marker, what happened, and optionally why.

    `detail` is dimmed rather than dropped. The messages worth reading are
    usually the ones with a reason attached, and a reason on its own line is a
    reason people scroll past.
    """
    line = Text.assemble(_marker(kind), "  ", (message, ""))
    if detail:
        line.append("  ")
        line.append(detail, style="dim")
    console.print(line)


def ok(message: str, detail: str = "") -> None:
    status("ok", message, detail)


def warn(message: str, detail: str = "") -> None:
    status("warn", message, detail)


def fail(message: str, detail: str = "") -> None:
    status("fail", message, detail)


def step(message: str, detail: str = "") -> None:
    status("step", message, detail)


def info(message: str, detail: str = "") -> None:
    status("info", message, detail)


def blank() -> None:
    console.print()


def heading(text: str) -> None:
    """A section break. Rich sizes the rule to the terminal."""
    console.rule(Text(text, style="bold cyan"), style="cyan", align="left")


def print_banner() -> None:
    """The wordmark, sized by Rich rather than by hand.

    Deliberately small. A twelve-line block-capital logo is charming once and
    then occupies most of a terminal every single run, and it was the thing that
    could not stay aligned.
    """
    title = Text.assemble(
        ("fpstune", "bold cyan"),
        ("  ", ""),
        (f"v{__version__}", "dim"),
    )
    tagline = Text(
        "Tunes Windows 11 to the ceiling this machine can reach",
        style="dim",
    )
    console.print()
    console.print(
        Panel(
            # Centred per line, not as a block. `Align.center` around a Group
            # centres the group's bounding box and leaves each line ragged
            # inside it, which looks like a mistake rather than a layout.
            Group(Align.center(title), Align.center(tagline)),
            border_style="cyan",
            padding=(1, 4),
            width=content_width(),
        )
    )
    console.print()


def details(rows: list[tuple[str, str]], *, title: str = "") -> None:
    """A key/value block whose columns line up because Rich measured them.

    Used for "here is what is running" and "here is what I found". The label
    column is dimmed so the values are what the eye lands on.
    """
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column(style="bold")
    for label, value in rows:
        table.add_row(label, value)

    if title:
        console.print(
            Panel(
                table,
                title=title,
                title_align="left",
                border_style="dim",
                width=content_width(),
            )
        )
    else:
        console.print(table)


def link(label: str, url: str) -> None:
    """A URL the terminal can make clickable, and that still reads if it cannot."""
    console.print(
        Text.assemble(
            _marker("step"),
            "  ",
            (f"{label}  ", ""),
            (url, "bold underline cyan link " + url),
        )
    )


def relay(prefix: str, line: str) -> None:
    """A line from a child process, tagged with whose it is, styled as the child styled it.

    ``Text.from_ansi`` keeps the child's colours — the API logger's palette,
    Vite's — where this console renders colour and drops the escapes where it
    cannot; markup is never interpreted, so a path or a ``[skipped]`` stays
    literal.
    """
    console.print(
        Text.assemble((f"[{prefix}] ", "dim"), Text.from_ansi(line)),
        highlight=False,
        soft_wrap=True,
    )


def panel(body: RenderableType, *, title: str = "", style: str = "cyan") -> None:
    console.print(
        Panel(body, title=title, title_align="left", border_style=style, width=content_width())
    )


def hint(lines: list[str], *, title: str = "What to do") -> None:
    """The instructions that follow a failure.

    Kept next to the failure rather than printed loose: an error whose fix is
    three unstyled lines below it reads as more error.
    """
    body = Text()
    for index, line in enumerate(lines):
        if index:
            body.append("\n")
        body.append(f"{index + 1}. ", style="bold cyan")
        body.append(line)
    console.print(
        Panel(body, title=title, title_align="left", border_style="yellow", width=content_width())
    )
