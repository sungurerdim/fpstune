"""Audio settings, and the endpoint machinery the hardware panel shares.

Every per-device state here lives on the endpoint itself, under
``MMDevices\\Audio\\{Render,Capture}\\{guid}``. The global HKCU flags
``DisableFXEffects`` and ``DisableExclusiveMode`` that earlier releases wrote are
read by nothing in the Windows audio stack, so they were retired without a guard:
a value nothing reads has no harmful state to restore.
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# =============================================================================
# Shared endpoint machinery
#
# Three settings and the hardware panel walk the MMDevices endpoint list, and the
# settings used to carry their own copy of the walk. That asymmetry is its own defect class here (#56): an
# observation narrower or wider than the action means verification passes over a
# state that was never reached. One scan, built once, used by both.
# =============================================================================

_MMDEV_SUBKEY = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio"
_MMDEV_BASE = f"HKLM:\\{_MMDEV_SUBKEY}"

# PKEY_AudioEndpoint_PhysicalSpeakers' sibling: the shared-mode format blob.
_FORMAT_KEY = "{f19f064d-082c-4e27-bc73-6882a1bb8e4c},0"

# PKEY_AudioEndpoint_Disable_SysFx. Lives under FxProperties, not Properties —
# reading Properties returns null on every endpoint and supports the opposite
# conclusion.
_SYSFX_KEY = "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5"

# The endpoint's device instance path, e.g. "{1}.BTHHFENUM\BTHHFPAUDIO\...". A raw
# device path, so it is identical in every locale — unlike the friendly name, which
# is translated.
_DEVICE_PATH_KEY = "{b3f8fa53-0004-438e-9003-51a46e139bfc},2"

# PKEY_AudioEndpoint_Supports_EventDriven_Mode's neighbours on the same GUID: ,3 is
# "allow applications to take exclusive control of this device" (DWORD, 1 allowed,
# 0 blocked; absent means allowed, the Windows default).
_EXCLUSIVE_KEY = "{b3f8fa53-0004-438e-9003-51a46e139bfc},3"

# PKEY_AudioEngine_OEMFormat: the format the driver itself declares as the
# endpoint's default, in the same PROPVARIANT + WAVEFORMATEX layout as _FORMAT_KEY.
_OEM_FORMAT_KEY = "{e4870e26-3cc5-4cd2-ba46-ca0a9a70ed04},3"

# The effects-chain slots under FxProperties: ,1 pre-mix and ,2 post-mix CLSIDs
# (the Vista-era LFX/GFX model), ,3 the property page, ,5-,7 the stream/mode/
# endpoint effects and ,13-,15 their composite lists. Any of them holding a value
# means the endpoint has a chain for Disable_SysFx to switch.
_FX_SLOT_PREFIX = "{d04e05a6-594b-4fb6-a80d-01af5eed7d1d}"

# Microsoft's own system effects — the pre-mix (LFX) and post-mix (GFX) objects
# that implement Loudness Equalization, Bass Boost and Virtual Surround. Loudness
# Equalization exists on an endpoint only when one of them sits in its chain; a
# vendor chain without them has no such effect for a property to switch.
_MS_SYSFX_CLSIDS = (
    "{62dc1a93-ae24-464c-a43e-452f824c4250}",
    "{637c490d-eee3-4c0a-973f-371958802da2}",
)

# The Loudness Equalization switch: a VT_BOOL PROPVARIANT whose bytes 8-9 are
# ff,ff when on and 00,00 when off. Absent is off.
_LEQ_KEY = "{fc52a749-4be9-4510-896e-966ba6525980},3"

# Endpoints whose audio configuration belongs to something other than Windows.
# Matched against the raw device instance path.
#
# Both entries are corrections rather than refinements: with either endpoint
# present the settings below could never reach their target, so they nagged
# forever while apply reported success over a write that did not survive.
#
# BTHHFENUM — Bluetooth hands-free. Measured: the same headset publishes two
# render endpoints,
#     BTHENUM\{0000110B-...}    48000 Hz  2ch   <- A2DP, the music path
#     BTHHFENUM\BTHHFPAUDIO     16000 Hz  1ch   <- hands-free, the voice path
# 0000110B is the A2DP Audio Sink UUID; BTHHFENUM is the hands-free enumerator.
# Hands-free is defined at 8 kHz (CVSD) or 16 kHz (mSBC) — 48 kHz is not a rate the
# profile has, so 16000 there is the correct value, not a mismatch to fix.
#
# ROOT\MEDIA — software mixers (SteelSeries Sonar, Voicemeeter, VB-Cable, Nahimic
# and the like). These are virtual endpoints published by a user-mode program that
# configures them itself, so their rate and their effects chain are that program's
# settings, not Windows defaults fpstune is entitled to overwrite. Measured on the
# host that reported the failure this exclusion exists for:
#     SteelSeries Sonar - Gaming   ROOT\MEDIA\0000   96000 Hz  8ch  Disable_SysFx=0
#     SteelSeries Sonar - Chat     ROOT\MEDIA\0000   48000 Hz  2ch
# Sonar runs its spatial-capable outputs at 96 kHz 7.1 deliberately, and its DSP
# chain is the product the user installed. Forcing either would be C3 — a tweak
# that can lower the ceiling is not a tweak.
_EXCLUDED_DEVICE_PATHS = ("BTHHFENUM", "ROOT\\MEDIA")

# Built once so no two commands can be given different exclusion lists.
_EXCLUDED_PATH_TEST = " -or ".join(
    f"[string]$p.$dev -like '*{fragment}*'" for fragment in _EXCLUDED_DEVICE_PATHS
)

# Writing an endpoint key needs a narrower open than any shell tool performs, and
# this is measured rather than reasoned. Under UAC, on this host:
#
#     Set-ItemProperty                      -> SecurityException, access denied
#     reg.exe add                           -> ERROR: access denied
#     OpenSubKey(sub, ReadWriteSubTree,
#                RegistryRights 'SetValue,QueryValues')
#                                           -> open OK, SetValue accepted, read back
#
# The ACL grants BUILTIN\Administrators exactly `SetValue, ReadKey` and NOT
# `CreateSubKey`. Set-ItemProperty and reg.exe both open with KEY_WRITE
# (SetValue|CreateSubKey), so the open is refused before any value is touched.
# Asking for only the rights the ACL actually grants succeeds.
#
# This is why the sample-rate setting used to report
# "error: N endpoint(s) could not be written" the moment a real endpoint was off
# rate: it had never been able to write one. An earlier note in the ledger read the
# same ACL and concluded permission was not the problem — the ACL reading was
# right, the conclusion was wrong. The permission that fails is on the *open*.
_MIN_RIGHTS_WRITER = (
    "$fpsHklm = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine','Registry64'); "
    "$fpsRw = [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree; "
    "$fpsRights = [System.Security.AccessControl.RegistryRights]'SetValue,QueryValues'; "
    "function Set-FpsEndpointValue($sub, $name, $value, $kind) { "
    "$k = $null; "
    "try { $k = $fpsHklm.OpenSubKey($sub, $fpsRw, $fpsRights) } catch { return $false }; "
    "if ($null -eq $k) { return $false }; "
    "try { $k.SetValue($name, $value, $kind); return $true } "
    "catch { return $false } "
    "finally { $k.Close() } }; "
)


def _endpoint_scan(flows: tuple[str, ...], property_subkey: str) -> str:
    """The endpoint walk both settings share, up to the point they diverge.

    Leaves `$ep`, `$p` (the Properties bag) and `$sub` (the endpoint's subkey path
    relative to HKLM, which is what the minimal-rights open needs) in scope, and
    has already skipped anything inactive or excluded.
    """
    return (
        f"$fmt = '{_FORMAT_KEY}'; $dev = '{_DEVICE_PATH_KEY}'; $sysfxKey = '{_SYSFX_KEY}'; "
        f"foreach ($flow in @({','.join(repr(f) for f in flows)})) {{ "
        f'foreach ($ep in (Get-ChildItem "{_MMDEV_BASE}\\$flow" -EA SilentlyContinue)) {{ '
        "if ((Get-ItemProperty $ep.PSPath -Name 'DeviceState' -EA SilentlyContinue).DeviceState "
        "-ne 1) { continue }; "
        f'$sub = "{_MMDEV_SUBKEY}\\$flow\\$($ep.PSChildName)"; '
        "$props = Join-Path $ep.PSPath 'Properties'; "
        "$p = Get-ItemProperty $props -EA SilentlyContinue; "
        f"if ({_EXCLUDED_PATH_TEST}) {{ continue }}; "
        f"$target = Join-Path $ep.PSPath '{property_subkey}'; "
    )


# PowerShell predicates over an FxProperties bag, shared by the settings below,
# the hardware panel's device list and the loudness route, so "this endpoint has
# an effects chain" and "Loudness Equalization is on" mean one thing everywhere.
_LEQ_CLSID_PATTERN = "|".join(clsid.strip("{}") for clsid in _MS_SYSFX_CLSIDS)
FX_HELPERS = (
    f"$fpsLeqKey = '{_LEQ_KEY}'; "
    "function Test-FpsFxChain($fx) { "
    "if (-not $fx) { return $false }; "
    "foreach ($pp in $fx.PSObject.Properties) { "
    f"if ($pp.Name -like '{_FX_SLOT_PREFIX},*' -and "
    "[string]::Join('', @($pp.Value)) -ne '') { return $true } }; "
    "return $false }; "
    "function Test-FpsMsSysFx($fx) { "
    "if (-not $fx) { return $false }; "
    "foreach ($pp in $fx.PSObject.Properties) { "
    f"if ($pp.Name -like '{_FX_SLOT_PREFIX},*' -and "
    f"[string]::Join(' ', @($pp.Value)) -match '{_LEQ_CLSID_PATTERN}') {{ return $true }} }}; "
    "return $false }; "
    "function Test-FpsLeqOn($fx) { "
    "if (-not $fx) { return $false }; "
    "$v = @($fx.$fpsLeqKey); "
    "return ($v.Count -ge 10 -and [int]$v[8] -eq 0xff -and [int]$v[9] -eq 0xff) }; "
)

# Render only, matching the setting's own copy ("every active output"). Capture
# effects are noise suppression and echo cancellation — what keeps a player's own
# voice intelligible to the team — so switching them off is a functional loss, not
# a latency gain, and this setting does not reach for them.
#
# Two endpoint states are skipped on purpose:
# * Loudness Equalization switched on. That is a per-device choice the user made
#   in the hardware panel (monitor speakers are the usual reason), and a bulk
#   "clean" that silently undid it is exactly the "LEQ keeps turning itself off"
#   report. The device card owns that endpoint's chain.
# * No Disable_SysFx value and no chain at all: nothing runs, nothing to switch.
# Absent Disable_SysFx *with* a chain is effects on — the value only exists once
# something has written it, and the chain runs until then.
_FX_SCAN = (
    FX_HELPERS
    + _endpoint_scan(("Render",), "FxProperties")
    + "$fx = Get-ItemProperty $target -EA SilentlyContinue; "
    "if (-not $fx) { continue }; "
    "if (Test-FpsLeqOn $fx) { continue }; "
    "$sysfx = $fx.$sysfxKey; "
    "if ($null -eq $sysfx -and -not (Test-FpsFxChain $fx)) { continue }; "
    "$active = ($sysfx -ne 1); "
)


# === Per-endpoint audio effects ===
# An output's effects chain is switched by PKEY_AudioEndpoint_Disable_SysFx on that
# endpoint and nothing else: the global HKCU "DisableFXEffects" flag earlier
# releases wrote is read by no part of the audio stack, so a machine could read
# fully optimized while a vendor chain kept smearing the footsteps.
#
# The write goes through a minimal-rights open (see _MIN_RIGHTS_WRITER): measured
# under UAC, Set-ItemProperty on FxProperties is refused, the narrower open is not.
# IMMDevice::OpenPropertyStore is the wrong API here — the store it returns is the
# endpoint's Properties, which does not hold the FX keys.
AUDIO_ENDPOINT_ENHANCEMENTS = SettingExecutor(
    id="audio:endpoint_enhancements",
    category=SettingCategory.AUDIO,
    display_name="Per-Output Audio Effects",
    short_name="Per-output audio effects",
    description="Per-device audio effects running on an output. They sit between the game and the "
    "speakers and smear the direction a footstep came from.",
    value_type=SettingValueType.CHOICE,
    choices=("clean", "effects_active"),
    # Windows' own state: a driver's effects chain runs until something switches it
    # off. Reset writes this, so it has to be stock, not the recommendation.
    default_value="effects_active",
    recommended_value="clean",
    requires_reboot=False,
    evidence_level="proven",
    risk_level="low",
    sources=[
        "https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/audio-processing-object-architecture"
    ],
    current_impact="Effects active: an output is running DSP that smears distance and direction cues",
    recommended_impact="Clean: every active output passes audio through unprocessed",
    scope=SettingScope.COMPLETE,
    category_order=3,
    perceptible_cost=("Per-device audio effects stop applying — the device plays the raw stream."),
    effect="Turns off per-device Windows effects on every active output",
    impact_scores={"latency_ms": -3, "stability": "high"},
    # Windows reads the flag when a stream opens, so a stream that is already
    # running keeps its old chain until it restarts. Said plainly rather than left
    # for the user to discover as "it did not work".
    risk_warning="An app that is already playing keeps the effects it started with until it is "
    "restarted, because Windows reads this flag when a stream opens. Outputs where you switched "
    "Loudness Equalization on in the hardware panel keep their effects, and outputs published by "
    "audio software such as SteelSeries Sonar, Voicemeeter or Nahimic are left alone: their "
    "processing is the product you installed.",
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$result = 'not_available'; " + _FX_SCAN + "if ($result -eq 'not_available') "
        "{ $result = 'clean' }; "
        "if ($active) { $result = 'effects_active' } "
        "} }; "
        "$result"
    ),
    detect_args={},
    value_map={},
    # Writes exactly the endpoints detect counts — the same scan, so neither can
    # reach further than the other (#56). Both directions: "clean" writes 1 where
    # a chain runs, reset writes Windows' 0 back where fpstune or anything else
    # switched one off.
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$want = %value%; "
        + _MIN_RIGHTS_WRITER
        + "$changed = 0; $failed = 0; $rejected = 0; "
        + _FX_SCAN
        + "if (($want -eq 1) -ne $active) { continue }; "
        "if (-not (Set-FpsEndpointValue \"$sub\\FxProperties\" $sysfxKey $want 'DWord')) "
        "{ $failed++; continue }; "
        # Read back rather than trust the write, the same discipline the sample-rate
        # setting learned the hard way.
        "$after = (Get-ItemProperty $target -EA SilentlyContinue).$sysfxKey; "
        "if ($after -eq $want) { $changed++ } else { $rejected++ } "
        "} }; "
        "if ($failed -gt 0) { 'error: ' + $failed + ' endpoint(s) could not be written' } "
        "elseif ($rejected -gt 0) { 'error: ' + $rejected + ' endpoint(s) did not keep the flag' } "
        "else { 'ok:' + $changed }"
    ),
    apply_args={},
    apply_value_map={"clean": 1, "effects_active": 0},
)

# === Exclusive mode, per endpoint ===
# Whether an application may open the device exclusively, bypassing the shared
# mixer — the lowest-latency path Windows has, used by audio tools and a few games.
# It is per endpoint ({b3f8fa53-...},3 under Properties); the global HKCU
# "DisableExclusiveMode" an earlier release wrote is read by nothing.
#
# Windows ships it allowed, and allowed costs nothing: shared-mode apps are not
# slowed by another app's right to go exclusive. So this is a guard (consequence
# 2): it reports and undoes an output where something blocked the path.
AUDIO_ENDPOINT_EXCLUSIVE_MODE = SettingExecutor(
    id="audio:endpoint_exclusive_mode",
    category=SettingCategory.AUDIO,
    display_name="Exclusive Mode Access",
    short_name="Exclusive mode access",
    description="Whether apps may take exclusive, mixer-free control of each input and output. "
    "Blocking it removes the lowest-latency audio path Windows has and gains nothing.",
    value_type=SettingValueType.CHOICE,
    choices=("allowed", "blocked"),
    default_value="allowed",
    recommended_value="allowed",
    requires_reboot=False,
    evidence_level="proven",
    risk_level="safe",
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/coreaudio/exclusive-mode-streams",
    ],
    current_impact="Blocked: at least one device refuses the exclusive, mixer-free audio path",
    recommended_impact="Allowed: apps that ask for exclusive low-latency audio can have it",
    scope=SettingScope.RECOMMENDED,
    category_order=2,
    effect="Restores the exclusive low-latency audio path Windows ships with",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$result = 'not_available'; "
        + _endpoint_scan(("Render", "Capture"), "Properties")
        + f"$excl = $p.'{_EXCLUSIVE_KEY}'; "
        "if ($result -eq 'not_available') { $result = 'allowed' }; "
        "if ($null -ne $excl -and $excl -isnot [array] -and $excl -eq 0) "
        "{ $result = 'blocked' } "
        "} }; "
        "$result"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$want = %value%; "
        + _MIN_RIGHTS_WRITER
        + "$changed = 0; $failed = 0; $rejected = 0; "
        + _endpoint_scan(("Render", "Capture"), "Properties")
        + f"$exclKey = '{_EXCLUSIVE_KEY}'; $excl = $p.$exclKey; "
        # Only a DWORD this scan can read is ever rewritten: an absent value is
        # already Windows' "allowed", and a value of another shape is not one this
        # setting understands.
        "if ($null -ne $excl -and $excl -is [array]) { continue }; "
        "$blocked = ($null -ne $excl -and $excl -eq 0); "
        "if (($want -eq 1) -ne $blocked) { continue }; "
        "if (-not (Set-FpsEndpointValue \"$sub\\Properties\" $exclKey $want 'DWord')) "
        "{ $failed++; continue }; "
        "$after = (Get-ItemProperty $props -EA SilentlyContinue).$exclKey; "
        "if ($after -eq $want) { $changed++ } else { $rejected++ } "
        "} }; "
        "if ($failed -gt 0) { 'error: ' + $failed + ' endpoint(s) could not be written' } "
        "elseif ($rejected -gt 0) { 'error: ' + $rejected + ' endpoint(s) did not keep the value' } "
        "else { 'ok:' + $changed }"
    ),
    apply_args={},
    apply_value_map={"allowed": 1, "blocked": 0},
)

# === Communications Ducking ===
# Windows' "stream attenuation": while a communication session is open, the OS
# lowers every other audio stream. The shipped default is a 80% reduction, so the
# moment a teammate speaks on Discord or in-game voice, footsteps and directional
# cues drop to a fifth of their volume — exactly the information a competitive
# player is listening for, silenced by the thing meant to help.
#
# Microsoft documents the four states and the control panel that writes them
# (Sound -> Communications). "Do nothing" leaves game audio alone; voice chat still
# plays, it simply stops attenuating everything else. Nothing is lost that the user
# cannot restore from the same setting, so this is zero-risk under C1.
#
# Attenuation is decided per communication session, so the change applies to the
# next session rather than to one already running.
COMMUNICATIONS_DUCKING = SettingExecutor(
    id="audio:communications_ducking",
    category=SettingCategory.AUDIO,
    display_name="Communications Ducking",
    short_name="Voice Ducking",
    description="Whether Windows lowers game audio while voice chat is active. The default cuts "
    "every other sound by 80%, so footsteps drop to a fifth of their volume whenever a teammate "
    "talks.",
    value_type=SettingValueType.CHOICE,
    choices=("mute_others", "reduce_80", "reduce_50", "do_nothing"),
    default_value="reduce_80",
    recommended_value="do_nothing",
    requires_reboot=False,
    current_impact="Reduce by 80%: Game audio drops to a fifth whenever voice chat is active",
    recommended_impact="Do nothing: Footsteps and directional cues keep full volume during voice chat",
    scope=SettingScope.RECOMMENDED,
    category_order=3,
    effect="Stops Windows muting game audio while voice chat is active",
    evidence_level="proven",  # Microsoft documents the mechanism and the four states
    risk_level="safe",
    # No latency claim: this changes gain, not timing. The numeric entry C2 asks for
    # is the attenuation this removes, which is the whole point of the setting.
    impact_scores={"latency_ms": 0.0, "audio_attenuation_removed": "80%"},
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/coreaudio/stream-attenuation",
    ],
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"Software\Microsoft\Multimedia\Audio",
        "name": "UserDuckingPreference",
        "hive": "HKCU",
    },
    # Absent means Windows' own default, which is the 80% reduction — not "unknown".
    value_map={
        0: "mute_others",
        "0": "mute_others",
        1: "reduce_80",
        "1": "reduce_80",
        2: "reduce_50",
        "2": "reduce_50",
        3: "do_nothing",
        "3": "do_nothing",
        None: "reduce_80",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"Software\Microsoft\Multimedia\Audio",
        "name": "UserDuckingPreference",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={
        "mute_others": 0,
        "reduce_80": 1,
        "reduce_50": 2,
        "do_nothing": 3,
    },
)

# Loudness Equalization is not a setting: it is a per-device choice made on the
# device's card in the hardware panel (api/routes/system_audio.py), off by default
# and never recommended — a compressor flattens the loudness differences that say
# how far away a sound is.
# === Shared-mode sample rate, every input and output ===
# The Windows audio engine mixes at each endpoint's configured rate, so content
# at a different rate is resampled on every buffer. 48 kHz is the rate to match:
# Intel HD Audio and AC'97 hardware has run natively at 48 kHz for two decades,
# game audio is authored at it, and 44.1 <-> 48 is a non-integer conversion.
#
# Measured on the dev machine before writing this: of six active render
# endpoints, three sat at 44100 (including the HDMI output feeding the monitor)
# and one at 96000/8ch, while the game device was already at 48000. So the
# mismatch is the normal state, not an edge case.
#
# Deliberately NOT claimed: a millisecond figure. Resampling costs CPU and a
# little buffering, and no isolated measurement of its latency was found.
# Deliberately NOT offered: 96/192 kHz. No game content exists at those rates,
# so they only force everything to be upsampled.
#
# Only endpoints whose driver declares 48 kHz as its own default format
# (PKEY_AudioEngine_OEMFormat) are counted or written. That is the hardware's
# answer to "does this device run at 48 kHz" (consequence 1), it makes 48 kHz
# Windows' own stock value for every endpoint in scope — so reset and apply agree
# and this is a drift guard — and it leaves alone a device whose driver defaults
# to something else, which a blind 48 kHz write could leave silent.
# Shared by detect and apply so the two cannot disagree about which endpoints count.
# That asymmetry is its own defect class in this codebase (#56): an observation
# narrower or wider than the action means verification passes over a state that was
# never reached.
_ENDPOINT_SCAN = (
    _endpoint_scan(("Render", "Capture"), "Properties") + "$b = $p.$fmt; "
    "if (-not $b -or $b.Length -lt 24) { continue }; "
    # A zero block alignment cannot be scaled into a byte rate, so apply skips it.
    # It lives here rather than in apply because detect used to count such an
    # endpoint as mismatched while apply passed over it — one more setting that
    # could never reach its own target.
    "$blockAlign = [BitConverter]::ToUInt16($b,20); "
    "if ($blockAlign -eq 0) { continue }; "
    f"$oem = $p.'{_OEM_FORMAT_KEY}'; "
    "if (-not $oem -or $oem.Length -lt 24 -or [BitConverter]::ToUInt32($oem,12) -ne 48000) "
    "{ continue }; "
)

# Blob layout confirmed by decoding real values rather than assumed: 48 bytes,
# an 8-byte PROPVARIANT header followed by a WAVEFORMATEXTENSIBLE. Offset 8 is
# 0xFFFE (WAVE_FORMAT_EXTENSIBLE), 10 nChannels, 12 nSamplesPerSec,
# 16 nAvgBytesPerSec, 20 nBlockAlign, 22 wBitsPerSample. A first attempt read
# the rate at offset 2 and got "1 Hz" on every endpoint, which is what an
# unverified layout looks like.
AUDIO_DEVICE_FORMAT = SettingExecutor(
    id="audio:device_format",
    category=SettingCategory.AUDIO,
    display_name="Device Sample Rate (48 kHz)",
    short_name="Audio sample rate",
    description="The rate each input and output runs at, for devices whose driver defaults to "
    "48 kHz. Anything else is resampled by the Windows mixer on every buffer, costing CPU.",
    value_type=SettingValueType.CHOICE,
    choices=("optimal", "mismatched"),
    default_value="optimal",
    recommended_value="optimal",
    requires_reboot=False,
    evidence_level="likely",
    risk_level="low",
    risk_warning="Counter-Strike 2 is a possible exception: one report has it requesting 44100 Hz "
    "and assuming it got it, producing a delay that grows the longer you play when the device runs "
    "at 48000 or higher. Source 1 was built around 44.1 kHz, so it is plausible, but it is a single "
    "report rather than a measurement — if CS2 audio drifts out of sync for you, set that device "
    "back to 44100 Hz in Sound Control Panel.",
    sources=[
        "https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/audio-signal-processing-modes",
        "https://linuxthings.co.uk/blog/cs2-audio-delay",
    ],
    current_impact="Mismatched: at least one device forces the mixer to resample every buffer",
    recommended_impact="Optimal: every 48 kHz-native device runs at 48 kHz, so nothing is resampled",
    scope=SettingScope.COMPLETE,
    category_order=4,
    effect="Matches every input and output to the 48 kHz rate games are authored at",
    impact_scores={"cpu_usage": 0.0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$result = 'not_available'; " + _ENDPOINT_SCAN + "if ($result -eq 'not_available') "
        "{ $result = 'optimal' }; "
        "if ([BitConverter]::ToUInt32($b,12) -ne 48000) { $result = 'mismatched' } "
        "} }; "
        "$result"
    ),
    detect_args={},
    value_map={},
    # nAvgBytesPerSec is recomputed, not left alone: a blob whose rate and byte
    # rate disagree is internally inconsistent, and the engine is entitled to
    # reject it. Channels and bit depth are preserved exactly — the device
    # already accepts that combination, and 48 kHz is the one rate essentially
    # every codec supports natively.
    # The write goes through Set-FpsEndpointValue, not Set-ItemProperty, and that
    # is the whole reason this setting can now change anything — see the note on
    # _MIN_RIGHTS_WRITER. A failed open is counted, never swallowed: swallowing a
    # denial is what made the enhancements setting report success over nothing.
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        _MIN_RIGHTS_WRITER + "$changed = 0; $failed = 0; $rejected = 0; " + _ENDPOINT_SCAN + "if "
        "([BitConverter]::ToUInt32($b,12) -eq 48000) { continue }; "
        "$new = [byte[]]$b.Clone(); "
        "[BitConverter]::GetBytes([uint32]48000).CopyTo($new,12); "
        "[BitConverter]::GetBytes([uint32](48000 * $blockAlign)).CopyTo($new,16); "
        "if (-not (Set-FpsEndpointValue \"$sub\\Properties\" $fmt $new 'Binary')) "
        "{ $failed++; continue }; "
        # Read the value back instead of trusting the write. Set-ItemProperty
        # returning without an exception is not evidence the value is there — that
        # assumption is what made this setting report success while every endpoint
        # stayed where it was. It cannot catch a revert that happens a second later;
        # the post-apply verify is what covers that.
        "$after = (Get-ItemProperty $props -EA SilentlyContinue).$fmt; "
        "if ($after -and $after.Length -ge 24 -and "
        "[BitConverter]::ToUInt32($after,12) -eq 48000) { $changed++ } else { $rejected++ } "
        "} }; "
        "if ($failed -gt 0) { 'error: ' + $failed + ' endpoint(s) could not be written' } "
        "elseif ($rejected -gt 0) { 'error: ' + $rejected + ' endpoint(s) did not keep 48 kHz' } "
        "else { 'ok:' + $changed }"
    ),
    apply_args={},
    apply_value_map={},
    # The script sets every endpoint to 48 kHz whatever it is asked for, so
    # "mismatched" is something to detect, never something to restore.
    unwritable_values=("mismatched",),
)

AUDIO_SETTINGS: list[SettingExecutor] = [
    AUDIO_ENDPOINT_ENHANCEMENTS,
    AUDIO_DEVICE_FORMAT,
    AUDIO_ENDPOINT_EXCLUSIVE_MODE,
    COMMUNICATIONS_DUCKING,
]
