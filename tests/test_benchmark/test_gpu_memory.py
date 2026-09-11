"""Three adapters, one of them rendering, and the two ways of getting it wrong.

A laptop reports the discrete GPU, the integrated one and a render-only device
as three instances of the same counter. Adding their dedicated usage together
answers a question nobody asked; averaging it reports the card doing the work as
a third of what it is doing. The reading is the busiest adapter, and the rest are
on the record.

The other guard here is about absence. A machine whose driver publishes no GPU
counters must not report nought megabytes in use — that is a measurement of
nothing dressed as an empty card, and the tab would show a fully free GPU on a
machine that never answered.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from fpstune.benchmark.gpu_memory import (
    BYTES_PER_MB,
    NO_ADAPTER,
    GpuMemoryBench,
    forget_counter_probe,
)
from fpstune.benchmark.suite import Bench

# The three instances this machine reports, in the shape the class returns. The
# names are LUIDs — Windows' own runtime identifier for an adapter — passed in
# as fixture input rather than read from the environment (C9).
_DISCRETE: dict[str, Any] = {
    "adapter": "luid_0x00000000_0x0679BD6A_phys_0",
    "dedicated": 939_376_640,
    "shared": 83_804_160,
    "committed": 1_095_127_040,
}
_RENDER_ONLY: dict[str, Any] = {
    "adapter": "luid_0x00000000_0x0000D884_phys_0",
    "dedicated": 0,
    "shared": 8192,
    "committed": 1_409_024,
}
_INTEGRATED: dict[str, Any] = {
    "adapter": "luid_0x00000000_0x0000C997_phys_0",
    "dedicated": 0,
    "shared": 352_030_720,
    "committed": 379_666_432,
}


@pytest.fixture(autouse=True)
def _fresh_probe() -> None:
    forget_counter_probe()


def _run(rows: list[dict[str, Any]], repeats: int = 2):
    with patch("fpstune.benchmark.gpu_memory.query_rows", return_value=(rows, "")):
        return GpuMemoryBench().run(repeats)


class TestTheBusiestAdapterIsTheAnswer:
    def test_the_card_doing_the_work_is_the_reading(self) -> None:
        """896 MB on the discrete card, not 896 divided between three."""
        result = _run([_INTEGRATED, _DISCRETE, _RENDER_ONLY])

        assert result.readings["vram_mb"].median == pytest.approx(
            939_376_640 / BYTES_PER_MB, abs=0.01
        )

    def test_a_second_busy_adapter_is_not_added_to_the_first(self) -> None:
        """A desktop with two cards has two separate pools, not one big one.

        Summed, a machine rendering on one card while a capture device holds
        memory on another would report a video memory figure larger than either
        card owns, and a `vram_mb` verdict built on it would be about a pool
        that does not exist.
        """
        second_card = dict(_DISCRETE)
        second_card["adapter"] = "luid_0x00000000_0x00051A2B_phys_0"
        second_card["dedicated"] = 400_000_000

        result = _run([_DISCRETE, second_card, _INTEGRATED])

        assert result.readings["vram_mb"].median == pytest.approx(
            939_376_640 / BYTES_PER_MB, abs=0.01
        )
        assert len(result.detail["adapters"]) == 3

    def test_shared_memory_is_its_own_reading(self) -> None:
        """Shared memory is system RAM the GPU borrowed, a different resource."""
        result = _run([_DISCRETE])

        assert result.readings["gpu_shared_mb"].median == pytest.approx(
            83_804_160 / BYTES_PER_MB, abs=0.01
        )

    def test_less_video_memory_in_use_is_the_improvement(self) -> None:
        """`vram_mb: -300` claims a fall, so the reading has to fall too."""
        assert _run([_DISCRETE]).readings["vram_mb"].improves_upward is False

    def test_every_adapter_is_kept_with_its_own_identifier(self) -> None:
        result = _run([_DISCRETE, _INTEGRATED])

        assert [row["adapter"] for row in result.detail["adapters"]] == [
            _DISCRETE["adapter"],
            _INTEGRATED["adapter"],
        ]


class TestAMachineWithNoCounterSaysSo:
    def test_no_adapter_instances_is_not_an_empty_card(self) -> None:
        with patch("fpstune.benchmark.gpu_memory.query_rows", return_value=([], "")):
            bench = GpuMemoryBench()
            available, why = bench.is_available()
            result = bench.run(2)

        assert not available
        assert why == NO_ADAPTER
        assert not result.ran
        assert result.reason == NO_ADAPTER

    def test_a_failed_query_carries_its_own_reason(self) -> None:
        with patch(
            "fpstune.benchmark.gpu_memory.query_rows",
            return_value=([], "Windows did not answer this query"),
        ):
            result = GpuMemoryBench().run(2)

        assert not result.ran
        assert result.reason == "Windows did not answer this query"

    def test_the_availability_probe_runs_once_per_session(self) -> None:
        """Opening the benchmarks tab must not cost a PowerShell start-up each time."""
        with patch(
            "fpstune.benchmark.gpu_memory.query_rows", return_value=([_DISCRETE], "")
        ) as query:
            GpuMemoryBench().is_available()
            GpuMemoryBench().is_available()

        assert query.call_count == 1


class TestItAsksWindowsInNamesThatAreNeverTranslated:
    def test_the_query_uses_the_wmi_class_rather_than_a_counter_path(self) -> None:
        """A counter path is localised; a class name is not.

        `typeperf "\\GPU Adapter Memory(*)\\Dedicated Usage"` reads the same
        bytes on this machine, and the escape from a translated path — the
        counter index, `\\10914(*)\\10918` — was rejected outright by typeperf
        with `Error: No valid counters.`, so the class is the only path that is
        locale-proof end to end.
        """
        from fpstune.benchmark.gpu_memory import SCRIPT

        assert "Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory" in SCRIPT
        assert "typeperf" not in SCRIPT

    def test_it_satisfies_the_bench_protocol(self) -> None:
        assert isinstance(GpuMemoryBench(), Bench)

    def test_it_declares_a_deadline_that_grows_with_repeats(self) -> None:
        bench = GpuMemoryBench()
        assert bench.timeout_seconds(20) > bench.timeout_seconds(2)
