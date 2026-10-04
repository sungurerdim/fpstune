"""The hardware panel's audio endpoint list.

The script itself needs Windows; what is pinned here is what it reads and how its
answer becomes `AudioDeviceInfo`. Each test names the report it guards against.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from fpstune.api.hardware import audio
from fpstune.api.hardware.audio import _AUDIO_SCRIPT, get_audio_devices

MONITOR = "{0.0.0.00000000}.{5f1c3e2a-9b7d-4c1e-8a2f-3d6b9e0c1a24}"
MONITOR_2 = "{0.0.0.00000000}.{7a2d4f6b-1c3e-4a5b-9d8f-0e1c2b3a4d5e}"
MIC = "{0.0.1.00000000}.{c3b2a1d0-e9f8-4a7b-8c6d-5e4f3a2b1c0d}"


def _detect(payload: object) -> list:
    with patch.object(audio, "run_powershell", return_value=(True, json.dumps(payload))):
        return get_audio_devices()


class TestTheScript:
    def test_it_walks_the_registry_not_only_the_ok_pnp_devices(self) -> None:
        """`Get-PnpDevice -Status OK` dropped disabled endpoints, so a device turned
        off from its card disappeared and could never be turned back on."""
        assert "Get-PnpDevice" not in _AUDIO_SCRIPT
        assert "if ($state -ne 1 -and $state -ne 2) { continue }" in _AUDIO_SCRIPT

    def test_two_devices_with_one_name_stay_two_devices(self) -> None:
        """Two identical monitors used to collapse into one card."""
        assert "seenNames" not in _AUDIO_SCRIPT

    def test_ids_are_full_endpoint_ids(self) -> None:
        assert '$id = "{0.0.$flowIndex.00000000}.$($ep.PSChildName)"' in _AUDIO_SCRIPT

    def test_loudness_support_is_microsofts_effects_in_the_chain(self) -> None:
        """ "Has an FxProperties key" offered a toggle on outputs where Windows has no
        Loudness Equalization to switch — the toggle "worked" and nothing changed."""
        assert "$leqSupported = Test-FpsMsSysFx $fx" in _AUDIO_SCRIPT
        assert "62dc1a93-ae24-464c-a43e-452f824c4250" in _AUDIO_SCRIPT

    def test_loudness_reads_on_only_when_it_can_play(self) -> None:
        """On with every effect disabled is a state Windows shows and never plays."""
        assert (
            "$leqEnabled = $leqSupported -and (Test-FpsLeqOn $fx) -and -not $effectsOff"
            in _AUDIO_SCRIPT
        )

    def test_the_default_device_is_read_not_hardcoded_false(self) -> None:
        assert "Role:0" in _AUDIO_SCRIPT
        assert "$r.IsDefault = $true" in _AUDIO_SCRIPT


class TestParsing:
    def test_every_endpoint_survives_including_a_disabled_twin(self) -> None:
        devices = _detect(
            [
                {
                    "Id": MONITOR,
                    "Name": "Speakers (NVIDIA High Definition Audio)",
                    "DeviceType": "Playback",
                    "IsEnabled": True,
                    "IsDefault": True,
                    "LeqSupported": True,
                    "LeqEnabled": True,
                },
                {
                    "Id": MONITOR_2,
                    "Name": "Speakers (NVIDIA High Definition Audio)",
                    "DeviceType": "Playback",
                    "IsEnabled": False,
                    "IsDefault": False,
                    "LeqSupported": False,
                    "LeqEnabled": False,
                },
                {
                    "Id": MIC,
                    "Name": "Mikrofon (Realtek(R) Audio)",
                    "DeviceType": "Recording",
                    "IsEnabled": True,
                    "IsDefault": True,
                    "LeqSupported": False,
                    "LeqEnabled": False,
                },
            ]
        )
        assert [d.id for d in devices] == [MONITOR, MONITOR_2, MIC]
        assert devices[0].is_default and devices[0].loudness_eq_enabled
        assert devices[1].is_enabled is False
        assert devices[2].name == "Mikrofon (Realtek(R) Audio)"

    def test_a_single_endpoint_object_is_a_list_of_one(self) -> None:
        devices = _detect({"Id": MIC, "Name": "Mic", "DeviceType": "Recording"})
        assert [d.id for d in devices] == [MIC]

    def test_an_entry_without_an_id_is_dropped_not_given_an_empty_one(self) -> None:
        """An empty id posts to /audio/device//enabled — a 404 the user sees as a
        broken toggle."""
        devices = _detect([{"Name": "Ghost"}, None, {"Id": MIC, "Name": "Mic"}])
        assert [d.id for d in devices] == [MIC]

    def test_failure_and_garbage_are_an_empty_list(self) -> None:
        with patch.object(audio, "run_powershell", return_value=(False, "access denied")):
            assert get_audio_devices() == []
        with patch.object(audio, "run_powershell", return_value=(True, "not json")):
            assert get_audio_devices() == []
        with patch.object(audio, "run_powershell", return_value=(True, "")):
            assert get_audio_devices() == []
