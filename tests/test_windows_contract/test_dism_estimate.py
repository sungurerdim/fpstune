"""The DISM reclaimable estimate is DISM's own number, read from invariant output.

The shipped parser searched every line of ``AnalyzeComponentStore`` for the
English words ``Reclaimable|Reduction|Cleanup`` *and* a size — a line DISM never
prints, in any language — so the cleanup row said "0 MB" on every machine, and
on a Turkish, German or French Windows it could not even have found the words.
The function now runs DISM with its documented ``/English`` global option and
sums the two lines StartComponentCleanup can actually free. What it cannot read
it reports as unavailable, never as a size (C11).
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.settings.executors.powershell_actions import (
    _CLEANUP_STATUS,
    _DISM_RECLAIMABLE_FUNCTION,
    ACTION_COMMANDS,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

# As DISM 10.0.26100 prints it with /English, trimmed of the progress bar.
ENGLISH_REPORT = [
    "Deployment Image Servicing and Management tool",
    "Version: 10.0.26100.1150",
    "",
    "Image Version: 10.0.26100.4652",
    "",
    "Component Store (WinSxS) information:",
    "",
    "Windows Explorer Reported Size of Component Store : 9.20 GB",
    "",
    "Actual Size of Component Store : 8.93 GB",
    "",
    "    Shared with Windows : 6.20 GB",
    "    Backups and Disabled Features : 2.56 GB",
    "    Cache and Temporary Data : 166.21 MB",
    "",
    "Date of Last Cleanup : 2026-08-15 12:00:00",
    "",
    "Number of Reclaimable Packages : 3",
    "Component Store Cleanup Recommended : Yes",
    "",
    "The operation completed successfully.",
]

# The same report as a Turkish Windows prints it without /English: the labels
# are the language's, the sizes are the same. Nothing English to match.
TURKISH_REPORT = [
    "Dağıtım Görüntüsü Hizmet ve Yönetim aracı",
    "Bileşen Deposu (WinSxS) bilgileri:",
    "Bileşen Deposunun Gerçek Boyutu : 8.93 GB",
    "    Windows ile Paylaşılan : 6.20 GB",
    "    Yedeklemeler ve Devre Dışı Özellikler : 2.56 GB",
    "    Önbellek ve Geçici Veriler : 166.21 MB",
    "Bileşen Deposu Temizlemesi Önerilir : Evet",
    "İşlem başarıyla tamamlandı.",
]

_PRELUDE = r"""
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
function dism.exe {
    $global:LASTEXITCODE = [int]$FpsFake.exit
    [string[]]$FpsFake.lines
}
"""

_CALL = "\n$mb = Get-DismReclaimableMB; if ($null -eq $mb) { 'NULL' } else { \"$mb\" }\n"


def _estimate(lines: list[str], exit_code: int = 0) -> str:
    return run_shipped_command(
        _PRELUDE + _DISM_RECLAIMABLE_FUNCTION + _CALL, {"lines": lines, "exit": exit_code}
    )


def test_the_estimate_is_backups_plus_cache_in_megabytes() -> None:
    """2.56 GB + 166.21 MB, DISM's own accounting of what the cleanup frees."""
    assert _estimate(ENGLISH_REPORT) == "2788"


def test_dism_is_asked_for_english_output() -> None:
    """The one switch that makes the labels the same on every Windows language."""
    assert "/English" in _DISM_RECLAIMABLE_FUNCTION
    assert "Reclaimable|Reduction|Cleanup" not in _DISM_RECLAIMABLE_FUNCTION


def test_a_localized_report_yields_no_number_rather_than_a_wrong_one() -> None:
    """If /English were ever dropped, the Turkish report must not read as 0 MB."""
    assert _estimate(TURKISH_REPORT) == "NULL"


def test_a_failed_run_is_unavailable_not_zero() -> None:
    """Exit 740 is what an unelevated process gets; it is not an empty store."""
    assert (
        _estimate(["Error: 740", "Elevated permissions are required to run DISM."], 740) == "NULL"
    )


def test_the_detect_script_uses_the_one_parser() -> None:
    """Only one place parses DISM's report, so no second reading can disagree."""
    assert _DISM_RECLAIMABLE_FUNCTION in _CLEANUP_STATUS
    # Defined once, called from the 'dism' branch; no private parser survives.
    assert _CLEANUP_STATUS.count("Get-DismReclaimableMB") >= 2
    assert "$line -match 'Reclaimable" not in _CLEANUP_STATUS


def test_the_cleanup_measures_nothing_of_its_own() -> None:
    """The apply used to bracket the run with two AnalyzeComponentStore passes.

    Measured elevated on the reporting machine: 43.0 s for the first and 34.7 s
    for the second, inside a run the user timed at about 108 s. Three quarters
    of the wait was measuring — and measuring something the app already has,
    since the row's own detect supplies the before and `_finalize_apply_response`
    re-detects after. Freed is the difference between two readings that are
    taken either way.
    """
    cleanup = ACTION_COMMANDS["dism_cleanup"]
    assert "AnalyzeComponentStore" not in cleanup
    assert "Get-DismReclaimableMB" not in cleanup
    assert "StartComponentCleanup" in cleanup


def test_the_cleanup_reports_a_failure_instead_of_claiming_success() -> None:
    """Exit 740 (needs elevation) must not read as a completed cleanup."""
    cleanup = ACTION_COMMANDS["dism_cleanup"]
    assert "$LASTEXITCODE -ne 0" in cleanup
    assert "exit 1" in cleanup
