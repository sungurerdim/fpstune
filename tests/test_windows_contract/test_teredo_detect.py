"""Teredo is read the same way on every system language.

The setting used to parse `netsh interface teredo show state` for its `Type :`
row. netsh prints row labels in the system language, so on a Turkish Windows
there was no such row and detection failed. The detect now reads the cmdlet's
`Type` property; this runs the shipped command on a real host and holds its
answer to the values the setting maps.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.settings.applicability import ABSENT_READINGS
from fpstune.settings.definitions.network import TEREDO
from fpstune.utils.powershell import run_powershell

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Get-NetTeredoConfiguration")


def test_the_shipped_detect_answers_a_value_the_setting_maps() -> None:
    ok, output = run_powershell(TEREDO.detect_command)
    assert ok, output
    reading = output.strip().splitlines()[-1].strip()
    assert reading in TEREDO.value_map or reading in ABSENT_READINGS, reading


def test_detect_never_reads_a_localized_label() -> None:
    assert "netsh" not in TEREDO.detect_command.lower()
    assert "show state" not in TEREDO.detect_command
