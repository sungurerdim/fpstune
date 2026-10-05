"""A Windows update is noticed once, and nothing else reads as one.

Updates put settings back to Windows' own values; the notice tells a user who
applied everything weeks ago why the scan now shows drift. A false alarm on a
first run, or after a build that could not be read, would teach them to ignore it.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from fpstune.utils import os_build
from fpstune.utils.os_build import check_build_change


def test_the_first_run_records_the_build_and_reports_no_change(tmp_path: Path) -> None:
    state = tmp_path / "os_build.json"

    answer = check_build_change(state, "26100.4061")

    assert answer.changed is False
    assert answer.previous is None
    assert json.loads(state.read_text(encoding="utf-8")) == {"build": "26100.4061"}


def test_a_new_cumulative_update_is_a_change_and_becomes_the_record(tmp_path: Path) -> None:
    state = tmp_path / "os_build.json"
    state.write_text(json.dumps({"build": "26100.4061"}), encoding="utf-8")

    answer = check_build_change(state, "26100.4202")

    assert (answer.previous, answer.current, answer.changed) == ("26100.4061", "26100.4202", True)
    assert check_build_change(state, "26100.4202").changed is False


def test_the_same_build_is_no_change(tmp_path: Path) -> None:
    state = tmp_path / "os_build.json"
    state.write_text(json.dumps({"build": "22631.5039"}), encoding="utf-8")

    assert check_build_change(state, "22631.5039").changed is False


def test_an_unreadable_build_neither_alarms_nor_overwrites_the_record(tmp_path: Path) -> None:
    state = tmp_path / "os_build.json"
    state.write_text(json.dumps({"build": "26100.4061"}), encoding="utf-8")

    answer = check_build_change(state, None)

    assert answer.changed is False
    assert json.loads(state.read_text(encoding="utf-8")) == {"build": "26100.4061"}


def test_a_corrupt_record_is_a_first_run_and_is_rewritten(tmp_path: Path) -> None:
    state = tmp_path / "os_build.json"
    state.write_text("{not json", encoding="utf-8")

    answer = check_build_change(state, "26100.4061")

    assert answer.changed is False
    assert json.loads(state.read_text(encoding="utf-8")) == {"build": "26100.4061"}


def test_the_route_answers_once_per_process(tmp_path: Path, monkeypatch) -> None:
    """A reload in the same session still sees the update the first call found."""
    from fpstune.api.main import create_app

    (tmp_path / "os_build.json").write_text(json.dumps({"build": "26100.4061"}), encoding="utf-8")
    monkeypatch.setattr("fpstune.utils.config.get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(os_build, "current_build", lambda: "26200.6584")
    monkeypatch.setattr(os_build, "_answer", None)

    client = TestClient(create_app())
    first = client.get("/api/os-build").json()
    second = client.get("/api/os-build").json()

    assert first == {"previous": "26100.4061", "current": "26200.6584", "changed": True}
    assert second == first
