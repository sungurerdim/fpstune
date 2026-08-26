"""One PowerShell for every cleanup size, not one per setting.

Each of the 33 cleanup settings ran the whole ~18 KB ``cleanup_status`` script
in its own process to answer one question about one folder. Measured cold on the
dev machine, that was 33 of the 57 processes a scan was responsible for — and
each one re-parsed the same helpers before touching a directory. Batched:

    before   cold scan settled at 8.00s, 57 processes (52 powershell, 5 netsh)
    after    cold scan settled at 5.01s, 25 processes (20 powershell, 5 netsh)

Sizing the folders still costs what it costs. What went away is 32 process
startups and 32 re-parses of the same script.

The batch must stay *asynchronous*: `dism /AnalyzeComponentStore` alone runs
30-60 s, so awaiting this would trade processes for a scan nobody sits through.

Equivalence was checked against the real machine before this landed — all 33
types, batch output identical to per-setting output, 0 mismatches. These tests
pin the structure that makes that possible, because a batch can stop batching
without any test noticing: the per-setting fallback produces the same values,
which is how this codebase shipped a dead batch twice.
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from fpstune.settings.cleanup_cache import CleanupSizeCache
from fpstune.settings.executors import ps_batch
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.settings.registry import SettingsRegistry


class TestTheSharedScriptStaysBatchable:
    """The batch reuses the shipped script. These pin what it relies on."""

    def test_it_ends_with_the_single_type_call_the_batch_cuts_at(self) -> None:
        """The batch derives its preamble by cutting here.

        Deriving rather than keeping a copy is deliberate: two copies of a 15 KB
        script would drift, and the drift would be invisible because both halves
        would still run.
        """
        assert ACTION_COMMANDS["cleanup_status"].rstrip().endswith(ps_batch._CLEANUP_CALL)

    def test_the_dispatch_is_a_function_so_it_can_be_asked_more_than_once(self) -> None:
        assert "function Get-CleanupStatus" in ACTION_COMMANDS["cleanup_status"]

    def test_it_carries_no_exit_or_write_host(self) -> None:
        """Either would make the shared session unusable.

        ``exit`` at the top level of a -Command script ends the whole session,
        blanking every type after it. ``Write-Host`` writes past the pipeline, so
        ``Out-String`` never sees it and the value is lost.
        """
        script = ACTION_COMMANDS["cleanup_status"]
        assert not re.search(r"(^|[;{(\s])exit\b", script)
        assert "write-host" not in script.lower()

    def test_the_shipped_settings_all_use_one_script_and_a_type(self) -> None:
        """If a cleanup ever stopped routing through here, the batch would miss it."""
        cleanups = [
            s
            for s in SettingsRegistry(discover_dynamic=False).get_all()
            if s.detect_command.strip() == "cleanup_status"
        ]
        assert len(cleanups) > 20, "the cleanup family shrank; check the batch still covers it"
        for setting in cleanups:
            assert setting.detect_args.get("type"), f"{setting.id} has no cleanup type to batch"


class TestTheGeneratedScript:
    def _script_for(self, types: tuple[str, ...]) -> str:
        captured: list[str] = []

        def fake_run(script: str, **_kwargs: object) -> tuple[bool, str]:
            captured.append(script)
            return False, ""

        with (
            patch.object(ps_batch.sys, "platform", "win32"),
            patch.object(ps_batch, "run_powershell", fake_run),
        ):
            ps_batch._fetch_cleanup_sizes(types)
        return captured[0] if captured else ""

    def test_every_type_is_asked_in_the_one_session(self) -> None:
        script = self._script_for(("temp", "prefetch", "dism"))
        for cleanup_type in ("temp", "prefetch", "dism"):
            assert f"'{cleanup_type}'" in script

    def test_the_helpers_appear_once_not_once_per_type(self) -> None:
        """The whole point: parse the ~15 KB preamble a single time."""
        script = self._script_for(("temp", "prefetch", "dism"))
        assert script.count("function Get-DirSizeBytes") == 1

    def test_the_single_type_call_is_replaced_not_left_in(self) -> None:
        """Leaving it would run one arbitrary type twice and emit a stray line."""
        assert "%type%" not in self._script_for(("temp",))

    def test_a_quote_in_a_type_cannot_break_out_of_its_string(self) -> None:
        """Types are ours today; a script that only works on trusted input is a
        trap for whoever adds the first one that is not."""
        script = self._script_for(("we'ird",))
        assert "'we''ird'" in script

    def test_one_type_failing_does_not_lose_the_others(self) -> None:
        """A per-type try/catch, so a folder that throws costs only itself."""
        script = self._script_for(("temp", "dism"))
        assert "catch" in script


class TestParsing:
    def _fetch(self, output: str, types: tuple[str, ...] = ("temp",)) -> dict[str, str]:
        with (
            patch.object(ps_batch.sys, "platform", "win32"),
            patch.object(ps_batch, "run_powershell", lambda *_a, **_k: (True, output)),
        ):
            return ps_batch._fetch_cleanup_sizes(types)

    def test_a_normal_answer_is_read(self) -> None:
        payload = f'{ps_batch.DETECT_JSON_MARKER}\n{{"temp":"ready|56 MB"}}'
        assert self._fetch(payload) == {"temp": "ready|56 MB"}

    def test_output_written_before_the_marker_is_skipped(self) -> None:
        """A cmdlet that talks to the host would otherwise cost every type.

        This is the same guard the shared detect batch needs, and the reason it
        exists there: one chatty command made the whole document unparseable.
        """
        payload = f'WARNING: something\n{ps_batch.DETECT_JSON_MARKER}\n{{"temp":"ready|1 MB"}}'
        assert self._fetch(payload) == {"temp": "ready|1 MB"}

    def test_unparseable_output_answers_nothing_rather_than_something(self) -> None:
        """Every setting then falls back to its own process — today's behaviour,
        which is right. A wrong size would be worse than a slow one."""
        assert self._fetch("not json at all") == {}

    def test_a_failed_run_answers_nothing(self) -> None:
        with (
            patch.object(ps_batch.sys, "platform", "win32"),
            patch.object(ps_batch, "run_powershell", lambda *_a, **_k: (False, "")),
        ):
            assert ps_batch._fetch_cleanup_sizes(("temp",)) == {}

    def test_an_empty_reading_is_dropped(self) -> None:
        """An empty string is not an answer, and would mark the setting resolved."""
        payload = f'{ps_batch.DETECT_JSON_MARKER}\n{{"temp":"","dism":"ready|0 MB"}}'
        assert self._fetch(payload, ("temp", "dism")) == {"dism": "ready|0 MB"}

    def test_no_types_asks_nothing(self) -> None:
        assert ps_batch._fetch_cleanup_sizes(()) == {}


class TestTheBatchCannotGoSilentlyDead:
    def test_a_changed_script_tail_is_reported_loudly(self) -> None:
        """The failure mode this codebase has shipped twice.

        If the shared script stops ending the way the batch assumes, the batch
        answers nothing and every cleanup falls back to its own process — same
        values, same green suite, silently 32 processes heavier. It has to say so.

        Captured with a handler on the module's own logger rather than caplog:
        fpstune's logging config sets propagate=False, so the record never
        reaches the root logger caplog listens on and the assertion would pass
        on an empty list forever.
        """
        import logging

        captured: list[str] = []

        class _Collect(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record.getMessage())

        handler = _Collect(level=logging.WARNING)
        ps_batch.logger.addHandler(handler)
        try:
            with (
                patch.object(ps_batch.sys, "platform", "win32"),
                patch.dict(ACTION_COMMANDS, {"cleanup_status": "something else entirely"}),
            ):
                assert ps_batch._fetch_cleanup_sizes(("temp",)) == {}
        finally:
            ps_batch.logger.removeHandler(handler)

        assert any("cannot be batched" in message for message in captured), (
            f"the batch went dead without saying so; logged: {captured}"
        )


class TestEveryClaimedSettingGetsAnOutcome:
    """A "calculating" entry has no TTL, so one left behind spins forever."""

    @pytest.fixture
    def cache(self) -> CleanupSizeCache:
        return CleanupSizeCache()

    def _run_batch(self, cache: CleanupSizeCache, sizes: dict[str, str]) -> list:
        from fpstune.settings.executors import powershell as ps

        settings = SettingsRegistry(discover_dynamic=False).get_all()
        cleanups = [s for s in settings if s.detect_command.strip() == "cleanup_status"]

        finished = []
        with (
            patch("fpstune.settings.cleanup_cache.cleanup_size_cache", cache),
            patch.object(ps_batch, "_fetch_cleanup_sizes", lambda _t: sizes),
            patch.object(ps.threading, "Thread", side_effect=lambda **kw: _Inline(kw, finished)),
            # One batch runs at a time process-wide, which is right in production
            # and makes this test depend on whatever ran before it: any other
            # test that runs a real scan starts a real batch thread, and while
            # that is alive this call returns without doing anything. Passed
            # locally and failed on CI for exactly that reason.
            patch.object(ps, "_cleanup_batch_running", False),
        ):
            ps.start_cleanup_size_batch(cleanups)
        return cleanups

    def test_a_batch_that_answers_nothing_still_resolves_every_setting(
        self, cache: CleanupSizeCache
    ) -> None:
        cleanups = self._run_batch(cache, {})

        stuck = [s.id for s in cleanups if cache.is_calculating(s.id)]
        assert stuck == [], (
            "these settings were marked calculating and never resolved; their "
            "spinner never stops, because a calculating entry has no TTL"
        )

    def test_answered_types_land_as_real_sizes(self, cache: CleanupSizeCache) -> None:
        cleanups = self._run_batch(cache, {"temp": "ready|56 MB"})

        temp = next(s for s in cleanups if s.detect_args.get("type") == "temp")
        entry = cache.get(temp.id)
        assert entry is not None
        assert entry["status"] == "ready"
        assert entry["bytes"] == 56 * 1024 * 1024


class _Inline:
    """Run a Thread's target immediately, so the test observes the outcome."""

    def __init__(self, kwargs: dict, finished: list) -> None:
        self._target = kwargs["target"]
        self._finished = finished

    def start(self) -> None:
        self._target()
        self._finished.append(True)
