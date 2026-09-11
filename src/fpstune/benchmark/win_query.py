"""One way to ask Windows a question and get a list of rows back.

Six instruments in this package — the event scan, the storage counters, the
process sampler, the GPU memory counter, the boot log and the PCIe link probe —
all ask Windows the same *kind* of question: run one short script, hand back
structured data. Each of them writing its own subprocess call, its own JSON
parse and its own "what does an empty answer mean" would be six places for the
same three mistakes, and the mistakes are not hypothetical:

*A single row is not a list.* ``ConvertTo-Json`` writes a bare object when the
pipeline produced one item and an array when it produced two, so a caller that
indexes the result works on a machine with two disks and raises on a machine
with one. Everything here is wrapped in ``@(...)`` and comes back as a list,
always — including the empty one.

*An error is not an empty reading.* PowerShell prints its refusals in the
system's own language, which is why nothing here matches on the text: the
answer is either parseable JSON or it is a named failure, and the raw text goes
to the log rather than into a reason a user reads (C4).

*A question Windows cannot answer here still has to say so.* Off Windows there
is no answer at all, and returning an empty list would let a bench report
"measured nothing" where the truth is "this instrument does not exist on this
platform".
"""

from __future__ import annotations

import json
import sys
from typing import Any

from fpstune.utils.logger import get_logger
from fpstune.utils.powershell import run_powershell

logger = get_logger()

NOT_WINDOWS = "this reading only exists on Windows"
"""Said by every instrument here when it is asked off Windows."""

UNREADABLE = "Windows did not answer this query"
"""Said when the command failed or wrote something that is not JSON.

Deliberately not the tool's own words. PowerShell answers in the system
language, so quoting it here would put Turkish in a user-facing English string
(C4) and would key a user's understanding to whichever locale the machine runs.
The verbatim text is logged instead, where a developer reading a debug log is
the only audience.
"""


def _parse(payload: str) -> Any | None:
    """The JSON in this output, or None.

    Tolerant of a leading line of noise — a progress record, a warning
    PowerShell decided to print on stdout — by falling back to the last line
    that parses on its own. Not tolerant of nonsense: an output with no JSON in
    it returns None rather than an empty result, because "nothing matched" and
    "the query failed" are different answers and only one of them is a reading.
    """
    text = payload.strip()
    if not text:
        # An empty pipeline prints nothing at all. That is a real answer — no
        # disks matched, no events in the window — and not a failure.
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def query_rows(
    script: str, *, timeout: int = 20, component: str = "benchmark"
) -> tuple[list[dict[str, Any]], str]:
    """Run one PowerShell expression and return its rows, or a reason.

    ``script`` is an expression, not a pipeline ending in ``ConvertTo-Json``:
    the wrapping is added here so every caller gets the same list-shaped answer
    and nobody has to remember ``@(...)``.

    Returns ``(rows, reason)``. A non-empty reason means the rows are empty
    because something went wrong, which is not the same as a query that matched
    nothing — that one returns ``([], "")``.
    """
    if sys.platform != "win32":
        return [], NOT_WINDOWS

    wrapped = f"@({script}) | ConvertTo-Json -Compress -Depth 4"
    ok, output = run_powershell(wrapped, timeout=timeout, component=component)
    if not ok:
        logger.debug("%s: PowerShell refused the query: %s", component, output)
        return [], UNREADABLE

    parsed = _parse(output)
    if parsed is None:
        logger.debug("%s: PowerShell answered with no JSON: %s", component, output)
        return [], UNREADABLE

    if isinstance(parsed, dict):
        return [parsed], ""
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)], ""
    logger.debug("%s: PowerShell answered with %r", component, parsed)
    return [], UNREADABLE
