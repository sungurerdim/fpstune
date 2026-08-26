"""The store that makes "undo fpstune's change" mean something.

`reset` writes a setting's `default_value` — the curated Windows stock value —
and that is not the same as undoing fpstune. On a machine that deliberately ran
a non-stock value, a reset silently discards the user's own configuration. Until
this store existed nothing in the codebase remembered that value: `safety/` held
System Restore points, which are whole-machine, and nothing else.

The one rule everything here turns on is **first write wins**. A store that let a
later scan overwrite an entry would record the value fpstune itself had just
applied, and "undo" would put the tweak back — a guarantee that silently means
its opposite, which is the failure mode this codebase keeps paying for.
"""

from __future__ import annotations

import json

import pytest

from fpstune.safety.originals import SCHEMA_VERSION, OriginalValues


@pytest.fixture
def store(tmp_path) -> OriginalValues:
    return OriginalValues(path=tmp_path / "originals.json")


class TestRecording:
    def test_a_first_reading_is_kept(self, store: OriginalValues) -> None:
        assert store.record_first_seen({"perf:numlock_default": "off"}) == 1
        assert store.get("perf:numlock_default") == "off"

    def test_a_later_scan_never_overwrites_it(self, store: OriginalValues) -> None:
        """The whole point. The second reading is fpstune's own handiwork."""
        store.record_first_seen({"perf:numlock_default": "off"})
        added = store.record_first_seen({"perf:numlock_default": "on"})

        assert added == 0
        assert store.get("perf:numlock_default") == "off", (
            "the second scan read the value fpstune had just applied; recording it "
            "would make undo re-apply the tweak it is supposed to remove"
        )

    def test_an_unread_setting_is_not_recorded(self, store: OriginalValues) -> None:
        """None means "not read", and an undo that writes None writes nothing."""
        assert store.record_first_seen({"perf:numlock_default": None}) == 0
        assert store.has("perf:numlock_default") is False

    def test_a_falsy_reading_is_still_a_reading(self, store: OriginalValues) -> None:
        """0 and "" are values; only None is an absence."""
        store.record_first_seen({"a:zero": 0, "b:empty": "", "c:false": False})
        assert store.get("a:zero") == 0
        assert store.get("b:empty") == ""
        assert store.get("c:false") is False

    def test_recording_many_at_once_counts_only_the_new_ones(self, store: OriginalValues) -> None:
        store.record_first_seen({"a:one": 1, "b:two": 2})
        assert store.record_first_seen({"a:one": 9, "c:three": 3}) == 1
        assert store.count() == 3


class TestForgetting:
    def test_a_landed_undo_frees_the_slot(self, store: OriginalValues) -> None:
        """Otherwise the store pins a value from an arbitrarily old session."""
        store.record_first_seen({"perf:numlock_default": "off"})
        assert store.forget("perf:numlock_default") is True
        assert store.get("perf:numlock_default") is None

        store.record_first_seen({"perf:numlock_default": "on"})
        assert store.get("perf:numlock_default") == "on"

    def test_forgetting_what_was_never_there_is_not_an_error(self, store: OriginalValues) -> None:
        assert store.forget("nothing:here") is False


class TestPersistence:
    def test_it_survives_a_restart(self, tmp_path) -> None:
        path = tmp_path / "originals.json"
        OriginalValues(path=path).record_first_seen({"perf:numlock_default": "off"})

        assert OriginalValues(path=path).get("perf:numlock_default") == "off"

    def test_a_restart_still_refuses_to_overwrite(self, tmp_path) -> None:
        """First-write-wins has to hold across sessions or it holds nowhere.

        The realistic sequence: scan, apply, close the app, reopen, scan again.
        If the reload lost the record, that second scan would overwrite the
        original with the applied value.
        """
        path = tmp_path / "originals.json"
        OriginalValues(path=path).record_first_seen({"perf:numlock_default": "off"})

        reopened = OriginalValues(path=path)
        assert reopened.record_first_seen({"perf:numlock_default": "on"}) == 0
        assert reopened.get("perf:numlock_default") == "off"

    def test_the_file_says_which_layout_it_is(self, tmp_path) -> None:
        path = tmp_path / "originals.json"
        OriginalValues(path=path).record_first_seen({"a:b": 1})

        written = json.loads(path.read_text(encoding="utf-8"))
        assert written["version"] == SCHEMA_VERSION
        assert written["values"]["a:b"]["value"] == 1
        assert "first_seen" in written["values"]["a:b"]

    def test_no_file_yet_is_not_an_error(self, tmp_path) -> None:
        assert OriginalValues(path=tmp_path / "absent.json").get("a:b") is None


class TestDamagedStore:
    """A store it cannot read must read as "no undo available", never as "clean"."""

    def test_corrupt_json_does_not_raise(self, tmp_path) -> None:
        path = tmp_path / "originals.json"
        path.write_text("{ this is not json", encoding="utf-8")

        assert OriginalValues(path=path).get("a:b") is None

    def test_an_unknown_layout_is_ignored_rather_than_guessed_at(self, tmp_path) -> None:
        """A future version's file must not be read with this version's rules."""
        path = tmp_path / "originals.json"
        path.write_text(json.dumps({"version": 99, "values": {"a:b": {"value": 1}}}), "utf-8")

        assert OriginalValues(path=path).get("a:b") is None

    def test_a_malformed_entry_is_dropped_not_returned(self, tmp_path) -> None:
        path = tmp_path / "originals.json"
        path.write_text(
            json.dumps({"version": SCHEMA_VERSION, "values": {"a:b": "bare string"}}), "utf-8"
        )

        assert OriginalValues(path=path).get("a:b") is None

    def test_an_unwritable_path_does_not_take_the_scan_down(self, tmp_path) -> None:
        """Recording is a convenience; failing it must not fail the user's scan."""
        blocked = tmp_path / "a-file-not-a-dir"
        blocked.write_text("", encoding="utf-8")

        store = OriginalValues(path=blocked / "originals.json")
        assert store.record_first_seen({"a:b": 1}) == 1  # held in memory
        assert store.get("a:b") == 1
