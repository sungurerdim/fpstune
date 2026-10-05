"""Every change fpstune made stays on record across runs.

Nothing remembered what fpstune did after it did it: a user who applied tweaks
last week could not see them again, and a guard that put a value back looked
exactly like an untouched setting.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpstune.safety import history
from fpstune.safety.history import ChangeJournal


def test_changes_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    ChangeJournal(path).record("network:nagle_algorithm", "apply", "disabled")
    ChangeJournal(path).record("network:nagle_algorithm", "undo", "enabled")

    reread = ChangeJournal(path)
    assert [(c.action, c.value) for c in reread.entries()] == [
        ("undo", "enabled"),
        ("apply", "disabled"),
    ]
    assert reread.latest()["network:nagle_algorithm"].action == "undo"


def test_the_journal_cannot_grow_without_bound(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(history, "MAX_ENTRIES", 3)
    journal = ChangeJournal(tmp_path / "history.json")
    for i in range(5):
        journal.record(f"system:s{i}", "apply", i)
    assert [c.setting_id for c in journal.entries()] == ["system:s4", "system:s3", "system:s2"]


def test_an_unreadable_file_is_set_aside_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text("{not json", encoding="utf-8")

    journal = ChangeJournal(path)
    journal.record("system:x", "apply", 1)

    kept = list(tmp_path.glob("history.unreadable-*.json"))
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == "{not json"
    assert json.loads(path.read_text(encoding="utf-8"))["entries"][0]["setting_id"] == "system:x"


class TestOnlyLandedChangesAreRecorded:
    """Recorded from the one post-write path, and only for what can be put back."""

    @staticmethod
    def _record(**setting) -> list:
        from fpstune.api.routes import settings as routes

        defaults = {"id": "system:x", "is_action": False, "is_readonly": False}
        routes._record_change(SimpleNamespace(**(defaults | setting)), "Applied", "off")
        return history.get_change_journal().entries()

    def test_a_tweak_is_recorded(self) -> None:
        assert [(c.setting_id, c.action, c.value) for c in self._record()] == [
            ("system:x", "apply", "off")
        ]

    @pytest.mark.parametrize("flag", ["is_action", "is_readonly"])
    def test_actions_and_advisories_are_not_history(self, flag: str) -> None:
        assert self._record(**{flag: True}) == []
