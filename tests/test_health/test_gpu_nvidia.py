"""The driver's own slowdown limit, and what to do when the board reports none.

`nvidia-smi -q -x` carries the temperature, the live margin to slowdown (`tlimit`),
the slowdown and shutdown thresholds and the clock event reasons in one document.
The tag names are the driver's and are the same on every Windows language; what
differs between boards is which of them the board fills in:

* some report a live margin (`gpu_temp_tlimit`) and some answer `N/A` — this
  development machine's laptop part does, and reports its slowdown threshold instead;
* a board that reports neither has no limit the driver gave, so its temperature is
  not judged, and that is a gap and not a clean bill (C11 rule 3);
* a thermal reason that is *Active* is the driver saying it is slowing down for heat.
"""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import patch

import pytest

from fpstune.health import gpu_nvidia
from fpstune.health.gpu_nvidia import NO_SMI, SMI_FAILED, NvidiaGpu, parse, read
from fpstune.health.model import Gap
from fpstune.health.thermal import assess

_REASONS = (
    "gpu_idle",
    "applications_clocks_setting",
    "sw_power_cap",
    "hw_slowdown",
    "hw_thermal_slowdown",
    "hw_power_brake_slowdown",
    "sync_boost",
    "sw_thermal_slowdown",
    "display_clocks_setting",
    "board_limit",
    "reliability",
)


def _gpu_xml(
    *,
    name: str = "NVIDIA GeForce RTX 3070 Laptop GPU",
    temp: str = "64 C",
    tlimit: str = "N/A",
    slow: str = "98 C",
    shutdown: str = "101 C",
    active: tuple[str, ...] = ("gpu_idle",),
    pci: str = "249D10DE",
    section: str = "clocks_event_reasons",
    prefix: str = "clocks_event_reason_",
) -> str:
    reasons = "".join(
        f"<{prefix}{r}>{'Active' if r in active else 'Not Active'}</{prefix}{r}>" for r in _REASONS
    )
    return (
        f"<gpu id='00000000:01:00.0'><product_name>{name}</product_name>"
        f"<uuid>GPU-79611379-e4cf-c923-b9a9-70b6036cb25f</uuid>"
        f"<pci><pci_device_id>{pci}</pci_device_id></pci>"
        f"<{section}>{reasons}</{section}>"
        f"<temperature><gpu_temp>{temp}</gpu_temp><gpu_temp_max>N/A</gpu_temp_max>"
        f"<gpu_temp_tlimit>{tlimit}</gpu_temp_tlimit>"
        f"<gpu_temp_max_threshold>{shutdown}</gpu_temp_max_threshold>"
        f"<gpu_temp_slow_threshold>{slow}</gpu_temp_slow_threshold>"
        f"<gpu_temp_max_gpu_threshold>105 C</gpu_temp_max_gpu_threshold>"
        f"<memory_temp>N/A</memory_temp></temperature></gpu>"
    )


def _document(*gpus: str) -> str:
    return f"<?xml version='1.0' ?><nvidia_smi_log><driver_version>617.42</driver_version>{''.join(gpus)}</nvidia_smi_log>"


def _read(*gpus: str):
    return read(lambda: (_document(*gpus), ""))


class TestParse:
    def test_the_board_this_was_written_against_reads_back_field_for_field(self) -> None:
        (gpu,) = parse(_document(_gpu_xml()))

        assert gpu == NvidiaGpu(
            name="NVIDIA GeForce RTX 3070 Laptop GPU",
            device_id="PCI\\VEN_10DE&DEV_249D",
            temperature_c=64.0,
            margin_c=None,
            slowdown_c=98.0,
            shutdown_c=101.0,
            active_reasons=frozenset({"gpu_idle"}),
        )

    def test_the_pci_id_has_the_device_in_the_high_half_and_the_vendor_in_the_low(self) -> None:
        (gpu,) = parse(_document(_gpu_xml(pci="220410DE")))

        assert gpu.device_id == "PCI\\VEN_10DE&DEV_2204"

    def test_a_board_with_no_pci_id_falls_back_to_its_uuid(self) -> None:
        (gpu,) = parse(_document(_gpu_xml(pci="")))

        assert gpu.device_id == "GPU-79611379-e4cf-c923-b9a9-70b6036cb25f"

    def test_not_available_is_none_never_zero(self) -> None:
        (gpu,) = parse(_document(_gpu_xml(temp="N/A", slow="N/A", shutdown="N/A")))

        assert (gpu.temperature_c, gpu.slowdown_c, gpu.shutdown_c) == (None, None, None)

    def test_a_decimal_comma_is_read_as_a_decimal_point(self) -> None:
        """Defence for a localised build: `64,5 C` is not 645 and not unreadable."""
        (gpu,) = parse(_document(_gpu_xml(temp="64,5 C")))

        assert gpu.temperature_c == 64.5

    def test_the_older_throttle_reason_section_is_read_too(self) -> None:
        (gpu,) = parse(
            _document(
                _gpu_xml(
                    active=("hw_thermal_slowdown",),
                    section="clocks_throttle_reasons",
                    prefix="clocks_throttle_reason_",
                )
            )
        )

        assert gpu.active_reasons == frozenset({"hw_thermal_slowdown"})

    def test_a_driver_with_no_reason_section_is_unmeasured_not_empty(self) -> None:
        text = _document(_gpu_xml()).replace("clocks_event_reasons", "something_else")
        (gpu,) = parse(text)

        assert gpu.active_reasons is None

    def test_two_boards_are_two_gpus(self) -> None:
        gpus = parse(
            _document(_gpu_xml(), _gpu_xml(name="NVIDIA GeForce GTX 1050", pci="1C8D10DE"))
        )

        assert [g.device_id for g in gpus] == ["PCI\\VEN_10DE&DEV_249D", "PCI\\VEN_10DE&DEV_1C8D"]

    @pytest.mark.parametrize("text", ["", "not xml at all", "<nvidia_smi_log><gpu>"])
    def test_garbage_is_no_gpus_rather_than_an_exception(self, text: str) -> None:
        assert parse(text) == []


class TestTheLimitIsTheDriversOwn:
    def test_a_board_reporting_only_its_slowdown_threshold_is_judged_against_that(self) -> None:
        snapshot = _read(_gpu_xml(temp="64 C", tlimit="N/A", slow="98 C"))

        (reading,) = snapshot.readings
        assert (reading.temperature_c, reading.limit_c) == (64.0, 98.0)
        assert reading.limit_source == "driver slowdown temperature"
        assert reading.critical_c == 101.0

    def test_a_live_margin_beats_the_static_threshold(self) -> None:
        """tlimit is the board's own current margin: limit = temperature + margin."""
        snapshot = _read(_gpu_xml(temp="80 C", tlimit="13 C", slow="98 C"))

        (reading,) = snapshot.readings
        assert reading.limit_c == 93.0
        assert reading.limit_source == "driver margin to slowdown"

    def test_a_shutdown_threshold_at_or_below_the_limit_is_not_kept_as_critical(self) -> None:
        snapshot = _read(_gpu_xml(slow="98 C", shutdown="N/A"))

        assert snapshot.readings[0].critical_c is None

    def test_a_board_that_reports_no_limit_at_all_is_a_gap_not_a_clean_bill(self) -> None:
        snapshot = _read(_gpu_xml(temp="101 C", tlimit="N/A", slow="N/A", shutdown="N/A"))
        result = assess([snapshot])

        assert result.findings == ()
        assert any(
            g.source == "nvidia_smi" and "publishes no limit" in g.reason for g in result.gaps
        )

    def test_a_board_that_reports_no_temperature_is_a_named_gap(self) -> None:
        snapshot = _read(_gpu_xml(temp="N/A"))

        assert snapshot.readings == ()
        assert snapshot.gaps == (
            Gap(
                "nvidia_smi",
                "nvidia-smi reports no temperature for NVIDIA GeForce RTX 3070 Laptop GPU",
            ),
        )


class TestOnlyHeatCountsAsHeat:
    @pytest.mark.parametrize("reason", ["hw_thermal_slowdown", "sw_thermal_slowdown"])
    def test_a_thermal_slowdown_is_a_throttle_reason(self, reason: str) -> None:
        snapshot = _read(_gpu_xml(temp="70 C", active=(reason,)))

        assert snapshot.readings[0].throttle_reasons == (reason,)
        result = assess([snapshot])
        assert [f.title_key for f in result.findings] == ["health.gpu.thermal_throttle"]

    @pytest.mark.parametrize(
        "reason",
        ["gpu_idle", "sw_power_cap", "hw_slowdown", "hw_power_brake_slowdown", "board_limit"],
    )
    def test_power_and_idle_reasons_are_not_heat(self, reason: str) -> None:
        """A power cap at full load is the governor working; an idle GPU is not slowed."""
        snapshot = _read(_gpu_xml(temp="70 C", active=(reason,)))

        assert snapshot.readings[0].throttle_reasons == ()
        assert assess([snapshot]).findings == ()


class TestWhenTheToolIsNotThere:
    def test_an_nvidia_adapter_without_nvidia_smi_is_a_gap(self) -> None:
        with patch.object(gpu_nvidia, "nvidia_smi", return_value=None):
            snapshot = read()

        assert snapshot.gaps == (Gap("nvidia_smi", NO_SMI),)

    def test_a_run_that_fails_is_a_gap_with_the_same_voice(self) -> None:
        with (
            patch.object(gpu_nvidia, "nvidia_smi", return_value="C:\\fake\\nvidia-smi.exe"),
            patch.object(gpu_nvidia.process_watch, "run", side_effect=OSError("denied")),
        ):
            snapshot = read()

        assert snapshot.gaps == (Gap("nvidia_smi", SMI_FAILED),)

    def test_a_stalled_run_is_a_gap_too(self) -> None:
        stalled = subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=1)
        with (
            patch.object(gpu_nvidia, "nvidia_smi", return_value="C:\\fake\\nvidia-smi.exe"),
            patch.object(gpu_nvidia.process_watch, "run", side_effect=stalled),
        ):
            snapshot = read()

        assert snapshot.gaps == (Gap("nvidia_smi", SMI_FAILED),)

    def test_a_non_zero_exit_is_a_gap(self) -> None:
        failed: Any = subprocess.CompletedProcess([], 9, stdout="", stderr="NVML error")
        with (
            patch.object(gpu_nvidia, "nvidia_smi", return_value="C:\\fake\\nvidia-smi.exe"),
            patch.object(gpu_nvidia.process_watch, "run", return_value=failed),
        ):
            snapshot = read()

        assert snapshot.gaps == (Gap("nvidia_smi", SMI_FAILED),)

    def test_the_real_command_asks_for_the_xml_document(self) -> None:
        ok: Any = subprocess.CompletedProcess([], 0, stdout=_document(_gpu_xml()), stderr="")
        with (
            patch.object(gpu_nvidia, "nvidia_smi", return_value="C:\\fake\\nvidia-smi.exe"),
            patch.object(gpu_nvidia.process_watch, "run", return_value=ok) as run,
        ):
            snapshot = read()

        assert run.call_args.args[0] == ["C:\\fake\\nvidia-smi.exe", "-q", "-x"]
        assert len(snapshot.readings) == 1
