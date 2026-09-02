"""Config files come back with the byte-level shape they went in with.

Every PowerShell writer here used to end in::

    [System.IO.File]::WriteAllText($p, $t, [System.Text.Encoding]::UTF8)

.NET builds that ``Encoding.UTF8`` with ``encoderShouldEmitUTF8Identifier:
true``, so the call **adds a BOM**. Measured 2026-08-30: a ``line1\\nline2\\n``
file went through it and came back ``\\xef\\xbb\\xbfLINE1\\nline2\\n``.

The files that lands on are real ones. MW3's ``options.4.cod23.cst`` is BOM-less
and pure LF; every Steam ``.vdf`` on the machine this was measured on is
BOM-less. Meanwhile HotS's ``Variables.txt`` and CS2's ``autoexec.cfg`` *do*
carry a BOM — so unconditionally writing without one breaks the other half.
Neither constant is correct, which is why the helper reads the answer off the
file. ``mw4_config.py`` already did this in Python; these tests hold the
PowerShell writers to the same rule.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from fpstune.settings.executors.powershell_actions import _CONFIG_IO_HELPERS, ACTION_COMMANDS

BOM = b"\xef\xbb\xbf"


class TestNoWriterBypassesTheHelper:
    """Static guard, so a new writer cannot reintroduce the bug unnoticed."""

    def test_no_command_writes_with_the_bom_emitting_encoding(self) -> None:
        """The helper's own body is excluded — it is the one legitimate caller.

        ``Write-ConfigText`` ends in ``WriteAllText`` with an explicitly
        constructed ``UTF8Encoding($emitBom)``, and ``Read-ConfigText`` uses
        ``Encoding]::UTF8.GetString``, which is decode-only and adds nothing.
        Matching on the raw text without stripping the helper flags every
        command that correctly uses it.
        """
        offenders = [
            name
            for name, script in ACTION_COMMANDS.items()
            if isinstance(script, str)
            and "WriteAllText" in script.replace(_CONFIG_IO_HELPERS, "")
            and "Encoding]::UTF8" in script.replace(_CONFIG_IO_HELPERS, "")
        ]
        assert offenders == [], (
            f"these commands write a BOM into whatever they touch: {offenders}. "
            "Use Write-ConfigText, which preserves the file's own BOM state."
        )

    def test_every_command_using_the_helper_also_defines_it(self) -> None:
        """A call without the definition is a runtime failure, not a wrong byte."""
        broken = [
            name
            for name, script in ACTION_COMMANDS.items()
            if isinstance(script, str)
            and ("Read-ConfigText" in script or "Write-ConfigText" in script)
            and "function Read-ConfigText" not in script
        ]
        assert broken == []

    def test_the_config_writers_are_all_covered(self) -> None:
        """Pins the set: these are the commands that rewrite a file someone else owns."""
        expected = {
            "cs2_cvar_toggle",
            "cs2_fps_max_toggle",
            "cs2_maxping_toggle",
            "cs2_sdr_toggle",
            "hots_variable_set",
            "mw3_options_toggle",
            "mw3_pause_rendering_toggle",
            "mw3_texture_toggle",
            "steam_config_vdf_toggle",
            "steam_localconfig_vdf_toggle",
        }
        actual = {
            name
            for name, script in ACTION_COMMANDS.items()
            if isinstance(script, str) and "Write-ConfigText" in script
        }
        assert actual == expected


@pytest.mark.skipif(sys.platform != "win32", reason="the helper is PowerShell")
class TestHelperBehaviourOnDisk:
    """What the helper actually does to bytes, run through PowerShell itself."""

    def _run(self, tmp_path: Path, target: Path) -> None:
        script = (
            _CONFIG_IO_HELPERS
            + f"""
            $p = '{target}'
            $c = Read-ConfigText $p
            $nl = Get-ConfigNewline $c
            $c = $c.TrimEnd() + "${{nl}}appended=1${{nl}}"
            Write-ConfigText $p $c
        """
        )
        script_path = tmp_path / "run.ps1"
        script_path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr

    def test_a_bomless_lf_file_stays_bomless_and_lf(self, tmp_path: Path) -> None:
        """MW3's options file and every Steam .vdf are this shape."""
        target = tmp_path / "options.4.cod23.cst"
        target.write_bytes(b"line1\nline2\n")

        self._run(tmp_path, target)

        raw = target.read_bytes()
        assert not raw.startswith(BOM)
        assert b"\r\n" not in raw
        assert raw.endswith(b"appended=1\n")

    def test_a_bom_crlf_file_keeps_its_bom_and_crlf(self, tmp_path: Path) -> None:
        """HotS's Variables.txt is this shape; dropping the BOM would be the mirror bug."""
        target = tmp_path / "Variables.txt"
        target.write_bytes(BOM + b"line1\r\nline2\r\n")

        self._run(tmp_path, target)

        raw = target.read_bytes()
        assert raw.startswith(BOM)
        assert raw.endswith(b"appended=1\r\n")
        # Every line ending is still CRLF — no bare LF crept in beside them.
        assert raw.count(b"\n") == raw.count(b"\r\n")

    def test_a_file_written_from_scratch_gets_no_bom(self, tmp_path: Path) -> None:
        """CS2's autoexec is created when absent; an unread file must not gain a BOM.

        This is the branch where no Read-ConfigText ran, so the helper falls back
        to $false rather than to whatever the previous call happened to leave.
        """
        target = tmp_path / "autoexec.cfg"
        script = (
            _CONFIG_IO_HELPERS
            + f"""
            Write-ConfigText '{target}' "fps_max 0`n"
        """
        )
        script_path = tmp_path / "fresh.ps1"
        script_path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr

        assert not target.read_bytes().startswith(BOM)
