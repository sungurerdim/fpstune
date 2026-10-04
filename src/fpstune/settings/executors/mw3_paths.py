"""Where MW3 (cod23) keeps its players directory.

Two folders are live. The standalone MW3 install writes
``Documents\\Call of Duty MWIII\\players``; installs folded into the Call of Duty
HQ launcher write ``Documents\\Call of Duty\\players``. Both hold a file named
``options.4.cod23.cst``, so the one the game last wrote is the one it reads.
Pinning either folder made every MW3 setting report "not installed", or edit a
file the game no longer reads, on half the machines.
"""

from __future__ import annotations

# Relative to Documents, newest-first preference broken by modification time.
MW3_PLAYERS_DIRS = ("Call of Duty MWIII/players", "Call of Duty/players")
MW3_OPTIONS_FILE = "options.4.cod23.cst"

# The same choice in PowerShell, for the detect commands and apply actions that
# run there. Leaves ``$docPath`` and ``$codPath`` set; ``$codPath`` falls back
# to the standalone folder so a missing file still reads as "not installed".
MW3_PLAYERS_PS = (
    "$docPath = [System.Environment]::GetFolderPath('MyDocuments'); "
    "$codPath = @('Call of Duty MWIII\\players', 'Call of Duty\\players') | "
    "ForEach-Object { Join-Path $docPath $_ } | "
    "Where-Object { Test-Path -LiteralPath (Join-Path $_ 'options.4.cod23.cst') } | "
    "Sort-Object { (Get-Item -LiteralPath (Join-Path $_ 'options.4.cod23.cst')).LastWriteTimeUtc } "
    "-Descending | Select-Object -First 1; "
    "if (-not $codPath) { $codPath = Join-Path $docPath 'Call of Duty MWIII\\players' }; "
)
