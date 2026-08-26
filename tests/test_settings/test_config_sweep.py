"""fpstune could not clean up after a setting it had removed.

Deleting a setting deletes the only thing that knew its marker, so whatever it
had already written into a game config stayed there — orphaned, invisible to
detection because nothing looks for it any more, and impossible to undo through
the product. A CS2 autoexec.cfg audited on 2026-08-23 held 23 fpstune blocks and
12 of them were orphaned; one had been sitting there since 2026-08-11.

The failure this file guards against is not "the sweep did not run". It is the
sweep running and taking a *live* block with it, which turns a cleanup into a
silent reset of settings the user still has applied.
"""

from __future__ import annotations

import pathlib
import threading
import time
from types import SimpleNamespace

import pytest

from fpstune.settings.executors import config_sweep


def block(marker: str, body: str) -> str:
    return f"// ===fpstune-{marker}-start===\n{body}\n// ===fpstune-{marker}-end===\n"


class TestOwnershipComesFromTheRegistry:
    def test_every_shipped_cs2_setting_is_counted_as_live(self) -> None:
        """The defect was a hand-written list going stale on the next removal.

        Reading the settings themselves makes "orphaned" mean "nothing ships
        this any more" by construction, so a removal is all it takes.
        """
        from fpstune.settings.definitions.game_configs import CS2_SETTINGS

        live = config_sweep.live_markers()
        for setting in CS2_SETTINGS:
            marker = (setting.apply_args or {}).get("marker") or (setting.detect_args or {}).get(
                "batch_marker"
            )
            assert marker in live, f"{setting.id} ships but its marker looks orphaned"

    def test_both_spellings_are_read(self) -> None:
        # `marker` is what the write path uses and `batch_marker` is what the
        # batched read path uses. A setting carrying only one of them would look
        # orphaned and get its block swept out from under it.
        class FakeSetting:
            apply_args = {"marker": "written_only"}
            detect_args: dict[str, str] = {}

        class OtherSetting:
            apply_args: dict[str, str] = {}
            detect_args = {"batch_marker": "read_only"}

        class FakeRegistry:
            @staticmethod
            def get_all() -> list[object]:
                return [FakeSetting(), OtherSetting()]

        assert config_sweep.live_markers(FakeRegistry()) == {"written_only", "read_only"}

    def test_the_marker_set_is_not_empty(self) -> None:
        # An empty set would make every block in the file look orphaned, and the
        # sweep would delete all of them while reporting success.
        assert config_sweep.live_markers(), "no markers read; the sweep would empty the file"


class TestALiveBlockIsNeverSwept:
    def test_a_live_marker_survives(self) -> None:
        text = block("cs2_autohelp", "cl_autohelp 0")
        swept, removed = config_sweep.sweep_text(text, {"cs2_autohelp"})

        assert removed == []
        assert swept == text, "a live block was rewritten by a sweep that should be a no-op"

    def test_only_the_orphan_goes(self) -> None:
        text = (
            block("cs2_autohelp", "cl_autohelp 0")
            + "\n"
            + block("snd_mixahead", "snd_mixahead 0.05")
        )
        swept, removed = config_sweep.sweep_text(text, {"cs2_autohelp"})

        assert removed == ["snd_mixahead"]
        assert "cl_autohelp 0" in swept
        assert "snd_mixahead" not in swept

    def test_the_users_own_lines_are_left_alone(self) -> None:
        # autoexec.cfg belongs to the player. Anything outside a marked block is
        # theirs, and a sweep that tidied it would be editing their config.
        text = "// my own settings\nsensitivity 1.9\n\n" + block(
            "snd_mixahead", "snd_mixahead 0.05"
        )
        swept, removed = config_sweep.sweep_text(text, set())

        assert removed == ["snd_mixahead"]
        assert "sensitivity 1.9" in swept
        assert "// my own settings" in swept


class TestTheBomTrap:
    def test_the_first_block_is_found_behind_a_byte_order_mark(self) -> None:
        """The trap that made a sweep report 23 of 24 and claim success.

        PowerShell writes this file through [System.Text.Encoding]::UTF8, which
        emits a BOM. The first block therefore starts BOM + "//", and an anchor
        of `^[ \\t]*//` misses it — silently, and only ever for block one.
        """
        text = "\ufeff" + block("snd_mixahead", "snd_mixahead 0.05")

        assert config_sweep.found_markers(text) == ["snd_mixahead"]
        swept, removed = config_sweep.sweep_text(text, set())
        assert removed == ["snd_mixahead"]
        assert "snd_mixahead" not in swept

    def test_a_file_on_disk_written_with_a_bom_reads_the_same(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "autoexec.cfg"
        target.write_text(block("cl_forcepreload", "cl_forcepreload 1"), encoding="utf-8-sig")

        assert target.read_bytes().startswith(b"\xef\xbb\xbf"), "fixture is not exercising the BOM"
        assert config_sweep.found_markers(target.read_text(encoding="utf-8-sig")) == [
            "cl_forcepreload"
        ]


class TestBlockBoundaries:
    def test_an_orphan_does_not_pair_with_the_next_settings_end_marker(self) -> None:
        """Without the back-reference this is how a sweep eats a live block.

        An unterminated orphan start would match forward to whatever end marker
        came next, and everything between — including a live setting's block —
        would go with it.
        """
        text = "// ===fpstune-orphan-start===\ndead_cvar 1\n" + block(
            "cs2_autohelp", "cl_autohelp 0"
        )
        swept, removed = config_sweep.sweep_text(text, {"cs2_autohelp"})

        assert removed == [], "an unterminated orphan is not a block and must not be guessed at"
        assert "cl_autohelp 0" in swept

    def test_two_orphans_in_a_row_both_go(self) -> None:
        text = block("dead_one", "a 1") + block("dead_two", "b 2")
        swept, removed = config_sweep.sweep_text(text, set())

        assert removed == ["dead_one", "dead_two"]
        assert swept.strip() == ""

    def test_the_file_does_not_grow_blank_lines_on_each_sweep(self) -> None:
        # A sweep that left its own gaps behind would drift the file further
        # apart every release.
        text = block("live", "a 1") + "\n\n" + block("dead", "b 2") + "\n\n" + block("live2", "c 3")
        once, _ = config_sweep.sweep_text(text, {"live", "live2"})
        twice, removed = config_sweep.sweep_text(once, {"live", "live2"})

        assert removed == []
        assert twice == once
        assert "\n\n\n" not in once


class TestSweepingTheRealFile:
    @pytest.fixture
    def staged(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
        target = tmp_path / "autoexec.cfg"
        target.write_text(
            "sensitivity 1.9\n\n"
            + block("cs2_autohelp", "cl_autohelp 0")
            + "\n"
            + block("snd_mixahead", "snd_mixahead 0.05"),
            encoding="utf-8-sig",
        )
        monkeypatch.setattr(config_sweep, "cs2_autoexec_path", lambda: target)
        return target

    def test_a_dry_run_reports_without_touching_the_file(self, staged: pathlib.Path) -> None:
        # The default, because this edits a file the user may also have edited
        # by hand and "show me first" is the only honest default for that.
        before = staged.read_bytes()
        result = config_sweep.sweep_cs2_autoexec(dry_run=True)

        assert result["status"] == "would_remove"
        assert result["orphaned"] == ["snd_mixahead"]
        assert result["removed"] == []
        assert staged.read_bytes() == before

    def test_the_write_backs_up_first(self, staged: pathlib.Path) -> None:
        original = staged.read_bytes()
        result = config_sweep.sweep_cs2_autoexec(dry_run=False)

        backup = staged.with_name(staged.name + config_sweep.BACKUP_SUFFIX)
        assert backup.is_file()
        assert backup.read_bytes() == original
        assert result["removed"] == ["snd_mixahead"]
        assert "snd_mixahead" not in staged.read_text(encoding="utf-8-sig")
        assert "cl_autohelp 0" in staged.read_text(encoding="utf-8-sig")

    def test_a_second_sweep_keeps_the_first_backup(self, staged: pathlib.Path) -> None:
        """First write wins, the same promise safety/originals.py makes.

        The valuable copy is the one from before fpstune first touched the file.
        Overwriting it on the next sweep would replace that with a copy fpstune
        had already edited — a backup of its own work.
        """
        config_sweep.sweep_cs2_autoexec(dry_run=False)
        backup = staged.with_name(staged.name + config_sweep.BACKUP_SUFFIX)
        first = backup.read_bytes()

        staged.write_text(block("another_dead", "x 1"), encoding="utf-8")
        config_sweep.sweep_cs2_autoexec(dry_run=False)

        assert backup.read_bytes() == first

    def test_a_clean_file_is_reported_clean_and_not_rewritten(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "autoexec.cfg"
        target.write_text(block("cs2_autohelp", "cl_autohelp 0"), encoding="utf-8")
        monkeypatch.setattr(config_sweep, "cs2_autoexec_path", lambda: target)
        before = target.read_bytes()

        result = config_sweep.sweep_cs2_autoexec(dry_run=False)

        assert result["status"] == "clean"
        assert result["removed"] == []
        assert result["backup"] is None, "a no-op must not spend the one backup slot"
        assert target.read_bytes() == before

    def test_no_cs2_is_not_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config_sweep, "cs2_autoexec_path", lambda: None)
        result = config_sweep.sweep_cs2_autoexec(dry_run=True)

        assert result["status"] == "not_installed"
        assert result["orphaned"] == []


class _FakeRegistry:
    """A registry whose only job is to declare which markers are live."""

    def __init__(self, markers: set[str]) -> None:
        self._markers = markers

    def get_all(self) -> list[object]:
        return [
            SimpleNamespace(apply_args={"marker": marker}, detect_args={})
            for marker in self._markers
        ]


class TestConcurrentWritersDoNotLoseUpdates:
    """The sweep is one more whole-file rewrite of a file every CS2 toggle also
    rewrites, and bulk apply runs 16 settings in parallel.

    Without one shared lock around the whole read-modify-write, the sweep and a
    toggle both read the pre-change file, each rewrites it from its own stale
    copy, and the second writer out silently drops the first one's change —
    while both report success. Same failure shape as
    test_mw4_config.py::test_neither_setting_is_lost, on a different file.
    """

    def _delay_reads_of(
        self, monkeypatch: pytest.MonkeyPatch, target: pathlib.Path, seconds: float = 0.3
    ) -> None:
        """Hold every reader of one file open long enough to overlap.

        Without the lock both threads sit inside the read at the same moment —
        exactly the interleaving that loses an update. With the lock the second
        thread cannot start its read until the first has written, so the same
        delay simply serializes.
        """
        real_read = pathlib.Path.read_text

        def slow_read(self: pathlib.Path, *args: object, **kwargs: object) -> str:
            data = real_read(self, *args, **kwargs)  # type: ignore[arg-type]
            if self == target:
                time.sleep(seconds)
            return data

        monkeypatch.setattr(pathlib.Path, "read_text", slow_read)

    def test_neither_the_sweep_nor_the_setting_write_is_lost(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "autoexec.cfg"
        target.write_text(
            block("cs2_autohelp", "cl_autohelp 0")
            + "\n"
            + block("snd_mixahead", "snd_mixahead 0.05"),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_sweep, "cs2_autoexec_path", lambda: target)
        self._delay_reads_of(monkeypatch, target)

        def toggle_writer() -> None:
            # The shape of every cs2_*_toggle script: read the whole file,
            # change its own block, write the whole file back — under the same
            # mutex the sweep holds.
            with config_sweep._autoexec_lock():
                text = target.read_text(encoding="utf-8")
                target.write_text(text.replace("cl_autohelp 0", "cl_autohelp 1"), encoding="utf-8")

        def run_sweep() -> None:
            config_sweep.sweep_cs2_autoexec(dry_run=False, registry=_FakeRegistry({"cs2_autohelp"}))

        failures: list[BaseException] = []

        def run(fn: object) -> None:
            try:
                fn()  # type: ignore[operator]
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                failures.append(exc)

        threads = [
            threading.Thread(target=run, args=(run_sweep,)),
            threading.Thread(target=run, args=(toggle_writer,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert failures == []
        content = target.read_text(encoding="utf-8")
        # Both survived: a rebuild from a stale copy would either resurrect the
        # orphan or revert the toggle's change, with both writers reporting
        # success.
        assert "cl_autohelp 1" in content
        assert "snd_mixahead" not in content

    def test_one_writer_finishes_before_the_next_starts(self) -> None:
        """The primitive itself, without a file: overlap is what must not happen."""
        events: list[str] = []

        def hold(name: str) -> None:
            with config_sweep._autoexec_lock():
                events.append(f"enter {name}")
                time.sleep(0.15)
                events.append(f"leave {name}")

        threads = [
            threading.Thread(target=hold, args=("a",)),
            threading.Thread(target=hold, args=("b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert len(events) == 4
        assert events[0].startswith("enter")
        assert events[1] == events[0].replace("enter", "leave")

    def test_the_mutex_name_matches_the_setting_writers(self) -> None:
        """One name, or no protection.

        The sweep only serializes against the cs2_*_toggle scripts if both
        sides spell the same mutex; a drifted spelling is two locks that never
        meet, which is indistinguishable from no lock in every test but this
        one.
        """
        from fpstune.settings.executors import powershell_actions

        assert config_sweep.CS2_AUTOEXEC_MUTEX in powershell_actions._MUTEX_GROUPS


class TestRegistryReuse:
    def test_live_markers_reuses_the_warm_api_singleton(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the warm registry singleton exists, the sweep must read
        markers off that one — it includes dynamically discovered settings, so
        a dynamic setting that ever gains a marker is counted live rather than
        swept — instead of constructing a second registry per call."""
        import fpstune.settings.registry_cache as registry_cache

        monkeypatch.setattr(registry_cache, "_registry", _FakeRegistry({"from_singleton"}))

        assert config_sweep.live_markers() == {"from_singleton"}
