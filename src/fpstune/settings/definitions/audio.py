"""Audio latency setting definitions.

Contains settings for reducing audio latency in Windows.
These settings are safe and reversible.
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
# Two settings walk the MMDevices endpoint list, and both used to carry their own
# copy of the walk. That asymmetry is its own defect class here (#56): an
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


# Render only, matching the setting's own copy ("every active output"). Capture
# endpoints carry the flag too, but nothing here has ever observed or written one,
# and widening the walk without widening the claim is the #56 mistake.
_FX_SCAN = (
    _endpoint_scan(("Render",), "FxProperties")
    + "$fx = Get-ItemProperty $target -EA SilentlyContinue; "
    "if (-not $fx) { continue }; "
    "$sysfx = $fx.$sysfxKey; "
    # Absent is not "effects on" — it means the driver publishes no chain to
    # disable. Both detect and apply skip it, so neither invents a value.
    "if ($null -eq $sysfx) { continue }; "
)


# === Audio Enhancements ===
# DSP processing (reverb, equalizer, etc.) adds latency
AUDIO_ENHANCEMENTS = SettingExecutor(
    id="audio:enhancements",
    category=SettingCategory.AUDIO,
    display_name="Audio Enhancements",
    description="Windows audio DSP effects (equalizer, reverb, loudness equalisation). Processing "
    "sits between the game and the speakers and smears the positional cues it is meant to sharpen.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: DSP runs on at least one output → added latency and smeared cues",
    recommended_impact="Disabled: raw output on every active endpoint → lowest latency",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=1,  # Primary audio latency setting
    effect="Disables Windows audio DSP effects on every active output",
    impact_scores={"latency_ms": -3, "stability": "high"},
    # Scope note, and it is deliberate. This setting observes and writes exactly
    # one thing: the global HKCU flag. The per-endpoint effects state is a real
    # and separate story — measured here, the global flag read 1 ("disabled")
    # while an active endpoint carried PKEY_AudioEndpoint_Disable_SysFx = 0 —
    # and fpstune reports that separately (audio:endpoint_enhancements) rather
    # than pretending this setting covers it.
    #
    # An earlier version of this setting did try to cover both, and it was wrong —
    # but not for the reason recorded at the time. The old note said the endpoint
    # flag "cannot be written". Corrected by measurement under UAC: it can, through
    # a minimal-rights open (see _MIN_RIGHTS_WRITER). What was true is that the two
    # mechanisms tried then both fail —
    #   * Set-ItemProperty on MMDevices\Audio\Render\*\FxProperties is refused
    #     because the open asks for KEY_WRITE and the ACL grants SetValue without
    #     CreateSubKey; the denial was then swallowed by -ErrorAction
    #     SilentlyContinue while apply returned 'ok'
    #   * IMMDevice::OpenPropertyStore(STGM_WRITE) succeeds, but the store it
    #     returns is the endpoint's `Properties`, which does not contain the FX
    #     keys at all
    # so apply reported success, wrote nothing, and verification correctly failed.
    # The split stands on its own merits regardless: this setting owns one global
    # HKCU flag, `audio:endpoint_enhancements` owns the per-endpoint chain, and
    # each observes exactly what it writes — which is what C6 and C8 ask for.
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Audio",
        "name": "DisableFXEffects",
        "hive": "HKCU",
    },
    # 0 or None = enhancements enabled, 1 = disabled
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Audio",
        "name": "DisableFXEffects",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 0, "disabled": 1},
)

# === Per-endpoint audio effects ===
# The finding this exists for: Windows' global "disable enhancements" flag does
# not govern an individual output's APO chain, so a machine can read fully
# optimized while a Loudness EQ is still smearing the footsteps it was turned on
# to reveal. Measured on the dev machine, with the global flag set to disabled.
#
# This shipped as advisory on the grounds that fpstune could not write it. The
# symptom was real and the mechanism was wrong: measured under UAC, an ordinary
# Set-ItemProperty on FxProperties is refused, but a minimal-rights open of the
# same key accepts the write and reads it back (see _MIN_RIGHTS_WRITER). So the
# setting applies now. The other half of the old note stands untouched — the store
# IMMDevice::OpenPropertyStore hands back does not contain the FX keys, which made
# it the wrong API rather than proof the state is unwritable.
AUDIO_ENDPOINT_ENHANCEMENTS = SettingExecutor(
    id="audio:endpoint_enhancements",
    category=SettingCategory.AUDIO,
    display_name="Per-Output Audio Effects",
    description="Whether any active output still has Windows enhancements switched on for that "
    "device specifically. The global switch does not cover these.",
    value_type=SettingValueType.CHOICE,
    choices=("clean", "effects_active"),
    default_value="clean",
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
    effect="Turns off per-device Windows effects on every active output",
    impact_scores={"latency_ms": -3, "stability": "high"},
    # Windows re-reads the flag when the endpoint is next opened, so a stream that
    # is already running keeps its old chain until it restarts. Said plainly rather
    # than left for the user to discover as "it did not work".
    risk_warning="An app that is already playing keeps the effects it started with until it is "
    "restarted, because Windows reads this flag when a stream opens. Outputs published by audio "
    "software such as SteelSeries Sonar, Voicemeeter or Nahimic are deliberately left alone: their "
    "processing is the product you installed, and that program would put its own setting back.",
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$result = 'not_available'; " + _FX_SCAN + "if ($result -eq 'not_available') "
        "{ $result = 'clean' }; "
        "if ($sysfx -eq 0) { $result = 'effects_active' } "
        "} }; "
        "$result"
    ),
    detect_args={},
    value_map={},
    # Writes exactly the endpoints detect counts — the same scan, so neither can
    # reach further than the other (#56). An endpoint with no value at all is left
    # alone by both: absent means the driver publishes no effects chain to disable,
    # and creating the value there would be acting on something never observed.
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        _MIN_RIGHTS_WRITER + "$changed = 0; $failed = 0; $rejected = 0; " + _FX_SCAN + "if "
        "($sysfx -eq 1) { continue }; "
        "if (-not (Set-FpsEndpointValue \"$sub\\FxProperties\" $sysfxKey 1 'DWord')) "
        "{ $failed++; continue }; "
        # Read back rather than trust the write, the same discipline the sample-rate
        # setting learned the hard way.
        "$after = (Get-ItemProperty $target -EA SilentlyContinue).$sysfxKey; "
        "if ($after -eq 1) { $changed++ } else { $rejected++ } "
        "} }; "
        "if ($failed -gt 0) { 'error: ' + $failed + ' endpoint(s) could not be written' } "
        "elseif ($rejected -gt 0) { 'error: ' + $rejected + ' endpoint(s) did not keep the flag' } "
        "else { 'ok:' + $changed }"
    ),
    apply_args={},
    apply_value_map={},
)

# === Exclusive Mode ===
# When enabled, apps can take exclusive control of audio device
# Can cause other apps to lose audio, but lower latency
EXCLUSIVE_MODE = SettingExecutor(
    id="audio:exclusive_mode",
    category=SettingCategory.AUDIO,
    display_name="Exclusive Audio Mode",
    description="Allow apps exclusive audio access. Lower latency but blocks other audio.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Apps can take exclusive control → lower latency but may block Discord/music",
    recommended_impact="Disabled: Shared audio → no audio conflicts, slight latency increase",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=2,  # Audio access mode
    effect="Manages audio device exclusivity to prevent audio conflicts",
    impact_scores={"latency_ms": 0.5, "stability": "high", "ux": "improved compatibility"},
    # Detection - This is per-device, we'll use a system-wide preference
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Audio",
        "name": "DisableExclusiveMode",
        "hive": "HKCU",
    },
    # 0 or None = exclusive enabled, 1 = disabled
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Audio",
        "name": "DisableExclusiveMode",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 0, "disabled": 1},
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

# All audio settings
# Note: Loudness Equalization (Volume Normalization) is managed per-device
# in the Hardware panel, not as a global setting here.
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
    description="The rate each input and output runs at. Anything that does not match is "
    "resampled by the Windows mixer on every buffer, which costs CPU for nothing.",
    value_type=SettingValueType.CHOICE,
    choices=("optimal", "mismatched"),
    default_value="optimal",
    recommended_value="optimal",
    requires_reboot=False,
    evidence_level="likely",
    risk_level="low",
    # Two honest caveats rather than one confident claim.
    risk_warning="Counter-Strike 2 is a possible exception: one report has it requesting 44100 Hz "
    "and assuming it got it, producing a delay that grows the longer you play when the device runs "
    "at 48000 or higher. Source 1 was built around 44.1 kHz, so it is plausible, but it is a single "
    "report rather than a measurement — if CS2 audio drifts out of sync for you, set that device "
    "back to 44100 Hz in Sound Control Panel. Note also that reset returns every device to 48 kHz "
    "rather than the rate it had before, because fpstune does not record the original.",
    sources=[
        "https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/audio-signal-processing-modes",
        "https://linuxthings.co.uk/blog/cs2-audio-delay",
    ],
    current_impact="Mismatched: at least one device forces the mixer to resample every buffer",
    recommended_impact="Optimal: every input and output runs at 48 kHz, so nothing is resampled",
    scope=SettingScope.COMPLETE,
    category_order=4,
    effect="Matches every input and output to the 48 kHz rate games are authored at",
    impact_scores={"cpu_usage": -1, "stability": "high"},
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
)

AUDIO_SETTINGS: list[SettingExecutor] = [
    AUDIO_ENHANCEMENTS,
    AUDIO_ENDPOINT_ENHANCEMENTS,
    AUDIO_DEVICE_FORMAT,
    EXCLUSIVE_MODE,
    COMMUNICATIONS_DUCKING,
]
