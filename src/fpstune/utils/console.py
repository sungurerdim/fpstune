"""The one console fpstune writes to.

There were two, and they disagreed. The logger emitted raw ANSI escapes after
deciding for itself that stdout was a terminal; Rich decided separately and, on
Windows, also *enabled* the virtual-terminal mode that makes those escapes mean
anything. So the log lines written before Rich's first output arrived as
literal garbage and the ones after it arrived correctly:

    ←[36mINFO ←[0m ←[2m|←[0m ←[35mapi   ←[0m ... fpstune API starting...
    INFO  | api                  | ... [OK] GET /ui/ -> 200

Same process, same handler, same run. The escapes were never wrong; the console
was not in a mode to interpret them yet.

One Console fixes both halves: it decides colour support once, and Rich turns on
whatever the platform needs the first time anything is printed — including for
the logger, which now goes through here rather than around it.

Living in `utils` rather than beside the CLI's presentation helpers is
deliberate: the logger is a low-level module and must not import from
`commands`. Both import from here instead.
"""

from __future__ import annotations

from rich.console import Console

# Long lines are hard to read and terminals are wide. Beyond about this many
# columns the eye loses the start of a line before it reaches the end, and a
# panel stretched across 120 columns is mostly border. Rich still wraps to the
# real width when it is *narrower* than this — the cap is a maximum, not a fixed
# size, so nothing is ever cut off on a small window.
MAX_WIDTH = 96


def _make_console() -> Console:
    return Console(
        # `soft_wrap=False` keeps Rich wrapping long lines rather than letting
        # the terminal do it mid-word.
        soft_wrap=False,
        # Rich reads the real terminal width; this only bounds it.
        width=None,
    )


console = _make_console()


def content_width() -> int:
    """How wide a panel or table should be: the terminal, capped."""
    return min(console.width, MAX_WIDTH)
