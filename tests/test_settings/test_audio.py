"""Audio settings, and the one that stops Windows silencing the game.

Windows' stream attenuation lowers every non-communication stream while a voice
session is open, and the shipped default is an 80% reduction. So the moment a
teammate speaks on Discord, footsteps and directional cues drop to a fifth of their
volume — the exact information a competitive player is listening for, removed by the
feature meant to help. `audio:communications_ducking` exposes the four states
Microsoft documents and recommends the one that leaves game audio alone.
"""

from __future__ import annotations

from fpstune.settings.base import SettingScope, SettingValueType
from fpstune.settings.definitions.audio import (
    _ENDPOINT_SCAN,
    AUDIO_DEVICE_FORMAT,
    AUDIO_ENDPOINT_ENHANCEMENTS,
    AUDIO_ENHANCEMENTS,
    AUDIO_SETTINGS,
    COMMUNICATIONS_DUCKING,
    EXCLUSIVE_MODE,
)


class TestAudioSettingsList:
    def test_every_audio_setting_is_registered(self) -> None:
        ids = [s.id for s in AUDIO_SETTINGS]
        assert ids == [
            AUDIO_ENHANCEMENTS.id,
            AUDIO_ENDPOINT_ENHANCEMENTS.id,
            AUDIO_DEVICE_FORMAT.id,
            EXCLUSIVE_MODE.id,
            COMMUNICATIONS_DUCKING.id,
        ]


class TestCommunicationsDucking:
    def test_recommends_leaving_game_audio_alone(self) -> None:
        assert COMMUNICATIONS_DUCKING.recommended_value == "do_nothing"

    def test_default_is_the_windows_default_not_the_recommendation(self) -> None:
        """`default_value` is what reset writes, so it must be Windows' own state.

        Windows ships the 80% reduction. Recording our recommendation here instead
        would make reset silently keep the tweak applied.
        """
        assert COMMUNICATIONS_DUCKING.default_value == "reduce_80"

    def test_absent_value_reads_as_the_windows_default(self) -> None:
        """A missing key is not "unknown" — it is the documented default behaviour.

        Mapping None to anything else would report a machine that has never touched
        the setting as either already optimized or undetectable.
        """
        assert COMMUNICATIONS_DUCKING.value_map[None] == "reduce_80"

    def test_all_four_documented_states_round_trip(self) -> None:
        """Microsoft documents four states; each must map both ways.

        The raw values are the radio buttons of Sound -> Communications:
        0 mute all, 1 reduce 80%, 2 reduce 50%, 3 do nothing.
        """
        expected_raw = {
            "mute_others": 0,
            "reduce_80": 1,
            "reduce_50": 2,
            "do_nothing": 3,
        }
        assert set(COMMUNICATIONS_DUCKING.choices) == set(expected_raw)
        for display, raw in expected_raw.items():
            assert COMMUNICATIONS_DUCKING.apply_value_map[display] == raw
            assert COMMUNICATIONS_DUCKING.value_map[raw] == display
            # Registry reads come back as int for REG_DWORD and str elsewhere, so
            # both spellings have to resolve — this is the #41 class.
            assert COMMUNICATIONS_DUCKING.value_map[str(raw)] == display

    def test_writes_the_key_the_sound_control_panel_writes(self) -> None:
        for args in (COMMUNICATIONS_DUCKING.detect_args, COMMUNICATIONS_DUCKING.apply_args):
            assert args["hive"] == "HKCU"
            assert args["path"] == r"Software\Microsoft\Multimedia\Audio"
            assert args["name"] == "UserDuckingPreference"

    def test_claims_no_latency_gain(self) -> None:
        """This changes gain, not timing.

        A non-zero `latency_ms` here would be added to the user-visible latency
        total on Home, which is how an invented -683ms figure got there before.
        """
        assert COMMUNICATIONS_DUCKING.impact_scores["latency_ms"] == 0.0

    def test_is_shown_as_a_choice_and_carries_a_source(self) -> None:
        assert COMMUNICATIONS_DUCKING.value_type == SettingValueType.CHOICE
        assert COMMUNICATIONS_DUCKING.scope == SettingScope.RECOMMENDED
        assert any("stream-attenuation" in s for s in COMMUNICATIONS_DUCKING.sources)


class TestEnhancementsScope:
    """Detect and apply must cover the same ground — no more, no less.

    An earlier version of `audio:enhancements` read the per-endpoint effects
    state as well as the global flag, and tried to write both. Apply swallowed
    the failure, returned "ok", and verification failed for the user with
    expected='disabled' detected='enabled'.

    The reason recorded at the time — "the FxProperties keys reject even an
    elevated write" — was wrong, and is corrected in
    `test_windows_contract/test_audio_endpoint_scope.py`: the keys are writable
    through a minimal-rights open. What holds is the split itself. This setting
    owns one global HKCU flag; `audio:endpoint_enhancements` owns the per-endpoint
    chain and now writes it. Each observes exactly what it writes.
    """

    SYSFX_KEY = "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5"

    def test_the_global_setting_observes_exactly_what_it_writes(self) -> None:
        assert AUDIO_ENHANCEMENTS.detect_args["name"] == "DisableFXEffects"
        assert AUDIO_ENHANCEMENTS.apply_args["name"] == "DisableFXEffects"
        assert AUDIO_ENHANCEMENTS.detect_args["hive"] == AUDIO_ENHANCEMENTS.apply_args["hive"]
        assert AUDIO_ENHANCEMENTS.detect_args["path"] == AUDIO_ENHANCEMENTS.apply_args["path"]

    def test_the_global_setting_does_not_reach_for_the_endpoint_flag(self) -> None:
        """Claiming it would reinstate an apply that reports success and writes nothing."""
        assert self.SYSFX_KEY not in AUDIO_ENHANCEMENTS.detect_command
        assert self.SYSFX_KEY not in AUDIO_ENHANCEMENTS.apply_command


class TestEndpointEnhancements:
    """It reports the finding, and — since the write mechanism was found — fixes it."""

    SYSFX_KEY = "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5"

    def test_it_is_no_longer_advisory(self) -> None:
        """The old `is_readonly` rested on "cannot be written", which was measured false.

        Set-ItemProperty is refused on these keys because it opens with KEY_WRITE
        while the ACL grants SetValue without CreateSubKey. A minimal-rights open
        writes them, so C1's "report what you cannot change" no longer applies.
        """
        assert AUDIO_ENDPOINT_ENHANCEMENTS.is_readonly is False
        assert AUDIO_ENDPOINT_ENHANCEMENTS.apply_command

    def test_the_write_does_not_go_through_set_itemproperty(self) -> None:
        """The precise regression: Set-ItemProperty here fails with access denied."""
        command = AUDIO_ENDPOINT_ENHANCEMENTS.apply_command
        assert "Set-ItemProperty" not in command
        assert "Set-FpsEndpointValue" in command

    def test_a_failed_write_is_reported_not_swallowed(self) -> None:
        command = AUDIO_ENDPOINT_ENHANCEMENTS.apply_command
        assert "$failed" in command
        assert "'error: '" in command

    def test_apply_reads_its_own_write_back(self) -> None:
        command = AUDIO_ENDPOINT_ENHANCEMENTS.apply_command
        assert "$after" in command
        assert "$rejected" in command

    def test_the_warning_states_the_restart_caveat_and_the_exclusion(self) -> None:
        """Both are things the user would otherwise experience as "it did not work"."""
        warning = AUDIO_ENDPOINT_ENHANCEMENTS.risk_warning or ""
        assert "restarted" in warning
        assert "Sonar" in warning

    def test_it_reads_the_key_that_actually_holds_the_state(self) -> None:
        command = AUDIO_ENDPOINT_ENHANCEMENTS.detect_command
        assert self.SYSFX_KEY in command
        assert "FxProperties" in command, (
            "the flag is under FxProperties; reading Properties returns null on "
            "every endpoint and would support the opposite conclusion"
        )
        assert "DeviceState" in command, "a disconnected endpoint's state is not evidence"

    def test_one_dirty_endpoint_decides_the_answer(self) -> None:
        command = AUDIO_ENDPOINT_ENHANCEMENTS.detect_command
        assert "$sysfx -eq 0" in command
        assert "$result = 'effects_active'" in command

    def test_every_reading_is_a_declared_choice(self) -> None:
        """Every state the command can report is one the setting declares.

        `not_available` is checked separately below: it is the one reading that
        must *not* be a choice, because it means there is no endpoint to have a
        state at all.
        """
        for token in ("clean", "effects_active"):
            assert token in AUDIO_ENDPOINT_ENHANCEMENTS.choices
            assert f"'{token}'" in AUDIO_ENDPOINT_ENHANCEMENTS.detect_command

    def test_the_absent_reading_is_emitted_but_never_offered(self) -> None:
        """A machine with no audio endpoint has no state here, only an absence.

        The command still has to say so — detection turns that into
        `is_applicable=False` and the setting disappears — but listing it in
        `choices` would put "not available" in the dropdown as something to pick,
        and would let the contract test accept a sentinel as a legitimate value.
        """
        assert "'not_available'" in AUDIO_ENDPOINT_ENHANCEMENTS.detect_command
        assert "not_available" not in AUDIO_ENDPOINT_ENHANCEMENTS.choices
        assert "not_available" not in AUDIO_ENDPOINT_ENHANCEMENTS.apply_value_map


class TestDeviceFormat:
    """48 kHz on every input and output, with the blob layout verified not assumed.

    A first attempt at this read the sample rate at offset 2 and got "1 Hz" on
    every endpoint. The layout is 48 bytes: an 8-byte PROPVARIANT header then a
    WAVEFORMATEXTENSIBLE, so offset 8 is the format tag, 12 the rate, 16 the byte
    rate, 20 the block align, 22 the bit depth.
    """

    # A real 44100 Hz / 32-bit / 2ch blob read from a live endpoint.
    BLOB = bytes.fromhex(
        "4100000001000000feff020044ac000020620500"
        "0800200016002000030000000100000000001000800000aa00389b71"
    )

    @staticmethod
    def _decode(b: bytes) -> dict:
        import struct

        return {
            "tag": struct.unpack_from("<H", b, 8)[0],
            "channels": struct.unpack_from("<H", b, 10)[0],
            "rate": struct.unpack_from("<I", b, 12)[0],
            "avg": struct.unpack_from("<I", b, 16)[0],
            "block": struct.unpack_from("<H", b, 20)[0],
            "bits": struct.unpack_from("<H", b, 22)[0],
        }

    def test_the_assumed_layout_decodes_a_real_blob(self) -> None:
        decoded = self._decode(self.BLOB)
        assert decoded["tag"] == 0xFFFE, "not WAVE_FORMAT_EXTENSIBLE — layout is wrong"
        assert decoded["rate"] == 44100
        assert decoded["avg"] == decoded["rate"] * decoded["block"], (
            "a real blob's byte rate must equal rate x block align; if this fails "
            "the offsets are wrong, not the device"
        )

    def test_patching_the_rate_keeps_the_blob_internally_consistent(self) -> None:
        """The byte rate must be recomputed, or the format contradicts itself."""
        import struct

        patched = bytearray(self.BLOB)
        block = self._decode(self.BLOB)["block"]
        struct.pack_into("<I", patched, 12, 48000)
        struct.pack_into("<I", patched, 16, 48000 * block)

        after = self._decode(bytes(patched))
        before = self._decode(self.BLOB)
        assert after["rate"] == 48000
        assert after["avg"] == after["rate"] * after["block"]
        # Channels and depth are preserved because the device already accepts
        # that combination; only the rate is in question.
        assert after["channels"] == before["channels"]
        assert after["bits"] == before["bits"]
        assert len(patched) == len(self.BLOB)

    def test_it_covers_capture_as_well_as_render(self) -> None:
        """An output at 48 kHz with a microphone at 44.1 breaks matched-rate apps."""
        for command in (AUDIO_DEVICE_FORMAT.detect_command, AUDIO_DEVICE_FORMAT.apply_command):
            assert "'Render','Capture'" in command.replace(" ", "")

    def test_apply_reads_the_same_offsets_detect_does(self) -> None:
        assert "ToUInt32($b,12)" in AUDIO_DEVICE_FORMAT.detect_command
        assert "CopyTo($new,12)" in AUDIO_DEVICE_FORMAT.apply_command
        assert "CopyTo($new,16)" in AUDIO_DEVICE_FORMAT.apply_command
        # The block alignment is read once, in the scan both commands share, so the
        # offset cannot drift between them. It used to be read separately in apply,
        # which is also why detect counted endpoints apply then passed over.
        assert "ToUInt16($b,20)" in _ENDPOINT_SCAN

    def test_detect_and_apply_walk_the_same_endpoints(self) -> None:
        """The #56 defect, one setting over: an observation narrower than the action.

        Both commands are built from one scan, so the DeviceState filter, the
        hands-free exclusion, the blob-length guard and the block-alignment guard
        are literally the same text. Two hand-written copies drifted apart before —
        apply skipped a zero block alignment that detect counted as a mismatch, so
        that endpoint made the setting permanently unsatisfiable.
        """
        assert _ENDPOINT_SCAN in AUDIO_DEVICE_FORMAT.detect_command
        assert _ENDPOINT_SCAN in AUDIO_DEVICE_FORMAT.apply_command

    def test_bluetooth_hands_free_endpoints_are_left_alone(self) -> None:
        """Hands-free is 8 or 16 kHz by definition; 48 kHz is not a rate it has.

        Measured on the dev machine: the same headset publishes A2DP at 48000/2ch and
        hands-free at 16000/1ch. Including the second one made the setting
        unsatisfiable on every machine with a Bluetooth headset paired — it reported
        `mismatched` forever and its apply claimed success over a write that never
        held.
        """
        assert "BTHHFENUM" in _ENDPOINT_SCAN

    def test_apply_reads_its_own_write_back(self) -> None:
        """Set-ItemProperty returning without an exception is not evidence.

        That assumption is what let this setting report success while every endpoint
        stayed where it was, which is the #40 shape in a different subsystem.
        """
        command = AUDIO_DEVICE_FORMAT.apply_command
        assert "$after" in command
        assert "ToUInt32($after,12) -eq 48000" in command
        assert "$rejected" in command

    def test_a_failed_write_is_reported_not_swallowed(self) -> None:
        """The enhancements setting reported success over a denied write. Not again."""
        command = AUDIO_DEVICE_FORMAT.apply_command
        assert "$failed" in command
        assert "'error: '" in command

    def test_the_write_does_not_go_through_set_itemproperty(self) -> None:
        """Measured under UAC: Set-ItemProperty and reg.exe are both denied here.

        Both open with KEY_WRITE (SetValue|CreateSubKey) while the endpoint ACL
        grants Administrators SetValue without CreateSubKey, so the open fails
        before any value is touched. This setting therefore could never write a
        hardware endpoint, and reverting to Set-ItemProperty would restore that.
        """
        command = AUDIO_DEVICE_FORMAT.apply_command
        assert "Set-ItemProperty" not in command
        assert "Set-FpsEndpointValue" in command
        assert "RegistryRights" in command

    def test_it_does_not_offer_rates_no_content_uses(self) -> None:
        for rate in ("96000", "192000", "176400"):
            assert rate not in AUDIO_DEVICE_FORMAT.apply_command

    def test_the_cs2_counter_evidence_is_stated_not_hidden(self) -> None:
        warning = AUDIO_DEVICE_FORMAT.risk_warning or ""
        assert "Counter-Strike 2" in warning
        assert "44100" in warning

    def test_no_invented_latency_figure(self) -> None:
        """Resampling costs CPU; no isolated measurement of its latency was found."""
        assert "latency_ms" not in AUDIO_DEVICE_FORMAT.impact_scores
