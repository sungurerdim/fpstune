"""`audio:device_format` against endpoints whose rate is not Windows' to set.

The failure this file exists for, reported from a real run:

    [FAIL] VERIFY FAILED Device Sample Rate (48 kHz):
           expected='optimal', detected='mismatched'

Measured on that host: every hardware output was already at 48 kHz and the only
endpoint reading 96000 was `SteelSeries Sonar - Gaming`, a virtual output on
`{1}.ROOT\\MEDIA\\0000` published by the Sonar app. Its ACL grants
`BUILTIN\\Administrators  SetValue`, so permission was never the reason the write
did not hold — the owning program simply puts its own format back. That makes the
setting permanently unsatisfiable, which is the same shape as the Bluetooth
hands-free case and the same shape as #56: fpstune observing more than it can act
on.

These tests run the shipped `detect_command` and `apply_command` verbatim against a
described host, rather than a copy of their logic. A copy only ever proves the copy
works, which is how seven defects in this codebase survived a green suite.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.settings.definitions.audio import (
    _EXCLUDED_PATH_TEST,
    _MIN_RIGHTS_WRITER,
    AUDIO_DEVICE_FORMAT,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

# The exclusion as it stood before the Sonar finding. Substituting it back is how
# each test proves it would fail against the previous command instead of passing
# for some unrelated reason.
_BLUETOOTH_ONLY_TEST = "[string]$p.$dev -like '*BTHHFENUM*'"

# Shadows the four cmdlets the shipped commands call, backed by the JSON payload.
# The format blob is built to the real 48-byte layout (8-byte PROPVARIANT header
# then a WAVEFORMATEXTENSIBLE) so the commands decode it exactly as they decode a
# live one — offset 12 is the rate, 16 the byte rate, 20 the block alignment.
#
# Every harness variable carries an `FpsFake` prefix, and that is load-bearing.
# PowerShell variable names are case-insensitive and `$script:Props` is the same
# variable as a bare `$props`, so the shipped scan's own `$props = Join-Path ...`
# silently replaced the harness's lookup table with a string. Every endpoint then
# failed the blob-length guard and every test read `not_available` — including the
# one that expects `not_available`, which passed for entirely the wrong reason.
# That is the trap this directory's conftest warns about, arriving through variable
# scope rather than a swallowed exception.
_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFakeHost = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

$FpsFakeFmtKey = '{f19f064d-082c-4e27-bc73-6882a1bb8e4c},0'
$FpsFakeDevKey = '{b3f8fa53-0004-438e-9003-51a46e139bfc},2'
$FpsFakeBase = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio'

$script:FpsFakeEndpoints = @{}
$script:FpsFakeProps = @{}

function New-FpsFakeFormatBlob {
    param([int]$Rate, [int]$Channels, [int]$Bits)
    $blockAlign = $Channels * ($Bits / 8)
    $buffer = New-Object byte[] 48
    [BitConverter]::GetBytes([uint16]0xFFFE).CopyTo($buffer, 8)
    [BitConverter]::GetBytes([uint16]$Channels).CopyTo($buffer, 10)
    [BitConverter]::GetBytes([uint32]$Rate).CopyTo($buffer, 12)
    [BitConverter]::GetBytes([uint32]($Rate * $blockAlign)).CopyTo($buffer, 16)
    [BitConverter]::GetBytes([uint16]$blockAlign).CopyTo($buffer, 20)
    [BitConverter]::GetBytes([uint16]$Bits).CopyTo($buffer, 22)
    ,$buffer
}

foreach ($FpsFakeEp in $FpsFakeHost.endpoints) {
    $FpsFakePath = "$FpsFakeBase\$($FpsFakeEp.flow)\$($FpsFakeEp.id)"
    $script:FpsFakeEndpoints[$FpsFakePath] = $FpsFakeEp
    $FpsFakeObj = New-Object psobject
    $FpsFakeObj | Add-Member -NotePropertyName $FpsFakeDevKey `
        -NotePropertyValue $FpsFakeEp.devpath
    if ($FpsFakeEp.rate -gt 0) {
        $FpsFakeObj | Add-Member -NotePropertyName $FpsFakeFmtKey -NotePropertyValue `
            (New-FpsFakeFormatBlob $FpsFakeEp.rate $FpsFakeEp.channels $FpsFakeEp.bits)
    }
    $script:FpsFakeProps["$FpsFakePath\Properties"] = $FpsFakeObj
}

function Get-ChildItem {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path)
    $prefix = $Path.TrimEnd('\') + '\'
    foreach ($key in $script:FpsFakeEndpoints.Keys) {
        # PSChildName as well as PSPath: apply builds the subkey path it opens from
        # the child name, so an object carrying only PSPath silently yields an empty
        # endpoint id and every write misses.
        if ($key.StartsWith($prefix)) {
            [pscustomobject]@{ PSPath = $key; PSChildName = $key.Substring($prefix.Length) }
        }
    }
}

function Get-ItemProperty {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path, [string]$Name)
    if ($Name -eq 'DeviceState') {
        $known = $script:FpsFakeEndpoints[$Path]
        if ($null -eq $known) { return $null }
        return [pscustomobject]@{ DeviceState = $known.state }
    }
    return $script:FpsFakeProps[$Path]
}

function Set-ItemProperty {
    [CmdletBinding()]
    param([Parameter(Position = 0)][string]$Path, [string]$Name, $Value, $Type, [switch]$Force)
    $target = $script:FpsFakeProps[$Path]
    if ($null -eq $target) { throw "no such key: $Path" }
    $target.$Name = $Value
}

"""


def _endpoint(
    ident: str,
    devpath: str,
    rate: int,
    *,
    flow: str = "Render",
    state: int = 1,
    channels: int = 2,
    bits: int = 32,
) -> dict:
    return {
        "id": ident,
        "flow": flow,
        "state": state,
        "devpath": devpath,
        "rate": rate,
        "channels": channels,
        "bits": bits,
    }


# The host that produced the reported failure, reduced to what the command reads.
_REALTEK = _endpoint(
    "{realtek}",
    r"{1}.HDAUDIO\FUNC_01&VEN_10EC&DEV_0274&SUBSYS_1D051147&REV_1000\4&15BCC161&0&0001",
    48000,
)
_SONAR_GAMING = _endpoint("{sonar-gaming}", r"{1}.ROOT\MEDIA\0000", 96000, channels=8, bits=24)
_SONAR_CHAT = _endpoint("{sonar-chat}", r"{1}.ROOT\MEDIA\0000", 48000, channels=2, bits=24)
_HANDS_FREE = _endpoint(
    "{bt-hfp}",
    r"{1}.BTHHFENUM\BTHHFPAUDIO\8&4DA94DB&0&97",
    16000,
    channels=1,
    bits=16,
)


def _detect(*endpoints: dict, shipped: bool = True) -> str:
    command = AUDIO_DEVICE_FORMAT.detect_command
    if not shipped:
        command = command.replace(_EXCLUDED_PATH_TEST, _BLUETOOTH_ONLY_TEST)
        assert command != AUDIO_DEVICE_FORMAT.detect_command, (
            "the exclusion clause this test substitutes is gone, so the "
            "before/after comparison proves nothing"
        )
    return run_shipped_command(_PRELUDE + command, {"endpoints": list(endpoints)})


# The shipped writer opens the real HKLM hive through the .NET registry API, which
# no cmdlet shadow can intercept. Whether that open is permitted was settled on real
# hardware under UAC, not here; what these tests decide is which endpoints apply
# walks and what it reports. So the writer is swapped for one that writes into the
# same fake store the rest of the harness reads.
_WRITER_STUB = (
    "function Set-FpsEndpointValue($sub, $name, $value, $kind) { "
    '$target = $script:FpsFakeProps["HKLM:\\$sub"]; '
    "if ($null -eq $target) { return $false }; "
    "$target.$name = $value; "
    "return $true }; "
)


def _apply(*endpoints: dict) -> str:
    command = AUDIO_DEVICE_FORMAT.apply_command
    stubbed = command.replace(_MIN_RIGHTS_WRITER, _WRITER_STUB)
    assert stubbed != command, (
        "the shipped writer this harness substitutes is gone, so these tests would "
        "be exercising a real registry write instead of the fake host"
    )
    return run_shipped_command(_PRELUDE + stubbed, {"endpoints": list(endpoints)})


class TestSoftwareMixerEndpoints:
    """A virtual output's rate belongs to the program that publishes it."""

    def test_the_reported_failure_no_longer_reproduces(self) -> None:
        assert _detect(_REALTEK, _SONAR_CHAT, _SONAR_GAMING) == "optimal"

    def test_the_previous_command_failed_on_exactly_this_host(self) -> None:
        """Without this, the test above could be passing for an unrelated reason."""
        assert _detect(_REALTEK, _SONAR_CHAT, _SONAR_GAMING, shipped=False) == "mismatched"

    def test_apply_does_not_write_an_endpoint_detect_ignores(self) -> None:
        """The #56 rule in both directions: never act on more than you observe.

        `ok:0` is the proof — apply walked the same host, found nothing it owns to
        change, and reported neither a change nor a failure.
        """
        assert _apply(_REALTEK, _SONAR_CHAT, _SONAR_GAMING) == "ok:0"


class TestExclusionDoesNotBlindTheSetting:
    """Excluding what cannot be held must not stop it reporting what can."""

    def test_a_real_output_off_rate_is_still_a_mismatch(self) -> None:
        off_rate = _endpoint("{aoc}", r"{1}.HDAUDIO\FUNC_01&VEN_10DE&DEV_009E", 44100)
        assert _detect(_REALTEK, _SONAR_GAMING, off_rate) == "mismatched"

    def test_apply_still_fixes_the_endpoint_it_owns(self) -> None:
        off_rate = _endpoint("{aoc}", r"{1}.HDAUDIO\FUNC_01&VEN_10DE&DEV_009E", 44100)
        assert _apply(_REALTEK, _SONAR_GAMING, off_rate) == "ok:1"

    def test_a_capture_endpoint_counts_too(self) -> None:
        mic = _endpoint(
            "{mic}", r"{1}.HDAUDIO\FUNC_01&VEN_10EC", 44100, flow="Capture", channels=1, bits=16
        )
        assert _detect(_REALTEK, mic) == "mismatched"


class TestBluetoothHandsFree:
    """The earlier exclusion, re-proved through the shared list rather than assumed."""

    def test_hands_free_is_not_a_mismatch(self) -> None:
        assert _detect(_REALTEK, _HANDS_FREE) == "optimal"

    def test_the_a2dp_endpoint_of_the_same_headset_is_still_checked(self) -> None:
        """Only the hands-free path is exempt; the music path is ordinary hardware."""
        a2dp = _endpoint(
            "{bt-a2dp}",
            r"{1}.BTHENUM\{0000110B-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002",
            44100,
            bits=16,
        )
        assert _detect(_REALTEK, a2dp) == "mismatched"


class TestEndpointsThatCarryNoAnswer:
    def test_an_inactive_endpoint_is_not_evidence(self) -> None:
        unplugged = _endpoint("{gone}", r"{1}.HDAUDIO\FUNC_01&VEN_8086", 44100, state=4)
        assert _detect(_REALTEK, unplugged) == "optimal"

    def test_a_host_with_nothing_checkable_reports_not_available(self) -> None:
        """Not `mismatched`, and not `optimal` — neither would be an observation.

        `not_available` is also what a dead harness answers, so this asserts the
        positive control first: the same two endpoints plus one real output must
        produce a real reading. Without that, a harness that sees no endpoints at
        all passes this test.
        """
        assert _detect(_HANDS_FREE, _SONAR_GAMING, _REALTEK) == "optimal"
        assert _detect(_HANDS_FREE, _SONAR_GAMING) == "not_available"
