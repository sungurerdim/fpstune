"""What get_cpu_detailed_info() makes of the detection script's report."""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

import fpstune.utils.detect as detect
from fpstune.utils.detect import CpuDetailedInfo

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

FULL = (
    "Name=Xeon Gold 6338\nSockets=2\nPhysicalCores=64\nLogicalCores=128\n"
    "BaseClock=2000\nL3Cache=49152\nPCores=64\nECores=0\nHybrid=False\n"
)
HYBRID = (
    "Name=Core i7-12700H\nSockets=1\nPhysicalCores=14\nLogicalCores=20\n"
    "BaseClock=2300\nL3Cache=24576\nPCores=6\nECores=8\nHybrid=True\n"
)
NO_TOPOLOGY = "Name=Some CPU\nSockets=1\nPhysicalCores=8\nLogicalCores=16\nBaseClock=3000\n"


def _cpu(monkeypatch: pytest.MonkeyPatch, stdout: str) -> CpuDetailedInfo:
    monkeypatch.setattr(detect, "_cpu_detailed_cache", None)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=stdout, stderr=""),
    )
    info = detect.get_cpu_detailed_info()
    monkeypatch.setattr(detect, "_cpu_detailed_cache", None)
    assert info is not None
    return info


class TestTheDeletedDuplicateStaysDeleted:
    def test_there_is_one_clock_and_it_is_the_rated_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Red against the old dataclass: max_clock_mhz existed and always
        equalled base — one WMI field wearing two names."""
        info = _cpu(monkeypatch, FULL)
        assert info.base_clock_mhz == 2000
        assert not hasattr(info, "max_clock_mhz")


class TestTopology:
    def test_a_hybrid_cpu_reports_its_split(self, monkeypatch: pytest.MonkeyPatch) -> None:
        info = _cpu(monkeypatch, HYBRID)
        assert (info.p_cores, info.e_cores, info.is_hybrid) == (6, 8, True)

    def test_no_topology_answer_is_unknown_not_non_hybrid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """B2 must refuse to place the RSS base without this answer, so
        "could not read" and "not hybrid" may never collapse into one."""
        info = _cpu(monkeypatch, NO_TOPOLOGY)
        assert info.is_hybrid is None

    def test_a_dual_socket_report_is_carried_whole(self, monkeypatch: pytest.MonkeyPatch) -> None:
        info = _cpu(monkeypatch, FULL)
        assert (info.sockets, info.physical_cores, info.logical_cores) == (2, 64, 128)
