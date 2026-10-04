"""The leftover sweep ends fpstune's own tools and never the user's.

`taskkill /IM PresentMon.exe` ended every PresentMon on the machine, including
one the user was recording with from their own install.
"""

from __future__ import annotations

from typing import Any

import pytest

from fpstune.benchmark import gpu_scene, own_processes, scheduler
from fpstune.benchmark.own_processes import ProcessImage, select_owned

ROOT = r"C:\Users\Player\.fpstune"
NAMES = ["presentmon.exe", "superposition.exe"]


def test_only_a_copy_under_fpstunes_own_folder_is_selected() -> None:
    images = [
        ProcessImage(100, ROOT + r"\benchmarks\presentmon\PresentMon.exe"),
        ProcessImage(200, r"C:\Program Files\Intel\PresentMon\PresentMon.exe"),
        ProcessImage(300, r"D:\Tools\PresentMon.exe"),
    ]

    assert select_owned(images, ROOT, NAMES, own_pid=1) == [100]


def test_a_sibling_folder_sharing_the_prefix_is_not_ours() -> None:
    """`.fpstune-old` starts with `.fpstune` as text but is another folder."""
    images = [ProcessImage(100, ROOT + r"-old\PresentMon.exe")]

    assert select_owned(images, ROOT, NAMES, own_pid=1) == []


def test_case_and_slash_spelling_do_not_hide_our_own_copy() -> None:
    images = [
        ProcessImage(
            100, r"c:/users/player/.FPSTUNE/benchmarks/superposition/bin/Superposition.exe"
        )
    ]

    assert select_owned(images, ROOT, NAMES, own_pid=1) == [100]


def test_an_unreadable_image_path_is_never_killed() -> None:
    """A process we could not open is one we cannot prove is ours."""
    images = [ProcessImage(100, "")]

    assert select_owned(images, ROOT, NAMES, own_pid=1) == []


def test_fpstune_itself_and_the_idle_process_are_never_selected() -> None:
    images = [
        ProcessImage(0, ROOT + r"\PresentMon.exe"),
        ProcessImage(42, ROOT + r"\PresentMon.exe"),
    ]

    assert select_owned(images, ROOT, NAMES, own_pid=42) == []


def test_another_executable_under_our_folder_is_left_alone() -> None:
    images = [ProcessImage(100, ROOT + r"\fpstune.exe")]

    assert select_owned(images, ROOT, NAMES, own_pid=1) == []


def test_the_sweep_kills_by_pid_and_closes_our_etw_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    killed: list[int] = []
    sessions: list[bool] = []
    monkeypatch.setattr(scheduler.sys, "platform", "win32")
    monkeypatch.setattr("fpstune.utils.config.get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(
        own_processes,
        "running_images",
        lambda _names: [
            ProcessImage(7, str(tmp_path / "benchmarks" / "presentmon" / "PresentMon.exe")),
            ProcessImage(8, r"C:\Program Files\PresentMon\PresentMon.exe"),
        ],
    )
    monkeypatch.setattr(own_processes, "kill_pid_tree", lambda pid: killed.append(pid) or True)
    monkeypatch.setattr(
        "fpstune.benchmark.presentmon.stop_etw_session", lambda: sessions.append(True)
    )

    assert scheduler.sweep_leftover_tools(["presentmon.exe"]) == 1
    assert killed == [7]
    assert sessions == [True]


def test_shutdown_ends_a_scene_that_is_still_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Closing fpstune mid-bench left a full-speed 3D scene on screen."""
    ended: list[str] = []

    class _Bench:
        def terminate_child(self) -> None:
            ended.append("scene")

    bench = _Bench()
    monkeypatch.setattr(gpu_scene, "_running", {bench})

    assert gpu_scene.terminate_running() == 1
    assert ended == ["scene"]
    assert gpu_scene._running == set()
