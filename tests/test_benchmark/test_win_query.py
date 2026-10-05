"""A stuck query says it was stuck; a refused one says it was refused.

Both used to read "Windows did not answer this query", so a bench panel could not
tell a machine that refused a reading from one whose query hung.
"""

from __future__ import annotations

from unittest.mock import patch

from fpstune.benchmark import win_query


def _query(answer: tuple[bool, str]) -> tuple[list, str]:
    with (
        patch.object(win_query.sys, "platform", "win32"),
        patch.object(win_query, "run_powershell", return_value=answer),
    ):
        return win_query.query_rows("Get-Thing", component="test")


def test_a_stall_reaches_the_reason_verbatim() -> None:
    rows, reason = _query((False, "PowerShell command stopped: no progress for 1 min"))
    assert rows == []
    assert reason == "PowerShell command stopped: no progress for 1 min"


def test_a_refusal_is_still_unreadable() -> None:
    rows, reason = _query((False, "Access is denied."))
    assert (rows, reason) == ([], win_query.UNREADABLE)


def test_rows_come_back() -> None:
    rows, reason = _query((True, '[{"a": 1}]'))
    assert (rows, reason) == ([{"a": 1}], "")
