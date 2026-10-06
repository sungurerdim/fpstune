"""The MSI rows reset to the driver's INF default and keep no record of what they overwrote.

The failure this guards: the earlier design stashed each device's prior MSISupported in
the registry as ``fpstuneOriginalMSISupported`` and reset restored it. A stored previous
value is a second way back (C6); reset now derives the driver's own default from the
installed INF and writes that. What each reading and write does is proven in
``tests/test_executors/test_msi_mode.py``; this file pins that the shipped rows are wired
to those actions and carry no script that could bring the stash back.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions.gpu import GPU_HARDWARE_SETTINGS
from fpstune.settings.definitions.network import create_msi_mode_setting
from fpstune.settings.executors.python_actions import PYTHON_ACTIONS, PYTHON_DETECTORS

GPU_MSI = next(s for s in GPU_HARDWARE_SETTINGS if s.id == "gpu-hardware:msi_mode")
NIC_MSI = create_msi_mode_setting(7, "Ethernet")


@pytest.mark.parametrize("setting", [GPU_MSI, NIC_MSI], ids=lambda s: s.id)
def test_the_row_is_a_python_detector_and_action_pair(setting: SettingExecutor) -> None:
    assert setting.detect_command in PYTHON_DETECTORS
    assert setting.apply_command in PYTHON_ACTIONS


@pytest.mark.parametrize("setting", [GPU_MSI, NIC_MSI], ids=lambda s: s.id)
def test_no_script_remains_that_could_record_or_restore_a_previous_value(
    setting: SettingExecutor,
) -> None:
    for text in (setting.detect_command, setting.apply_command, repr(setting.apply_args)):
        assert "Original" not in text
        assert "Set-ItemProperty" not in text
        assert "Remove-ItemProperty" not in text


def test_the_gpu_row_addresses_the_gpu_and_the_nic_row_its_own_interface() -> None:
    assert GPU_MSI.detect_args == GPU_MSI.apply_args == {"device": "gpu"}
    assert NIC_MSI.detect_args == NIC_MSI.apply_args == {"device": "nic", "ifindex": 7}


def test_reset_is_still_the_only_way_back_to_default() -> None:
    for setting in (GPU_MSI, NIC_MSI):
        assert setting.choices == ("default", "enabled")
        assert setting.default_value == "default"
        assert setting.recommended_value == "enabled"
