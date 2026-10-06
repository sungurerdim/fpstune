"""An apply and a background measurement never overlap, and an apply says so.

The scheduler holds `operation_lock.OPERATION_MUTEX` for a bench; a bulk apply
runs on many threads, so the apply side does not take the mutex — it waits for
the bench to give the machine back, then counts itself in flight for the
scheduler to see. And a bulk apply that changed something leaves the ledger's
sentinel behind, which is how an after-measurement happens without being asked
for.
"""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.api.routes import settings_apply
from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from tests.conftest import neutral_hardware_context


def _setting() -> SettingExecutor:
    return SettingExecutor(
        id="system:mouse_acceleration",
        category=SettingCategory.SYSTEM,
        display_name="Mouse Acceleration",
        description="Pointer precision scaling. Off keeps aim one-to-one with the mouse.",
        value_type=SettingValueType.CHOICE,
        choices=("off", "on"),
        default_value="on",
        recommended_value="off",
        detect_type=DetectType.POWERSHELL,
        detect_command="Get-Something",
        apply_type=DetectType.POWERSHELL,
        apply_command="Set-Something -Value '%value%'",
    )


def _finalize_stub(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
    return args, kwargs  # type: ignore[return-value]


class TestApplyWaitsForBench:
    def test_waits_for_a_running_bench_instead_of_refusing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bench mid-run is measuring; an apply landing then would change what
        it measures, so the apply waits. It used to give up after a fixed 30 s
        and refuse the user's change while a healthy measurement finished."""
        answers = iter([False, False, False, True])
        monkeypatch.setattr(settings_apply, "is_free", lambda: next(answers))
        monkeypatch.setattr(settings_apply, "_BENCH_POLL_SECONDS", 0.0)
        order: list[str] = []

        def _apply(*_a: Any, **_k: Any) -> tuple[bool, None]:
            order.append("applied")
            return True, None

        with (
            patch("fpstune.api.routes.settings_apply.CommandExecutor.apply", _apply),
            patch("fpstune.api.routes.settings._finalize_apply_response", _finalize_stub),
            patch("fpstune.utils.logger.log_activity", lambda m, *_: order.append(m)),
        ):
            args, _ = settings_apply.apply_and_finalize(_setting(), "off", MagicMock(), "Applied")

        assert args[3] is True
        assert order == [
            "Waiting for a background measurement to finish before applying",
            "applied",
        ]

    def test_counts_itself_in_flight_while_the_command_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scheduler's guard is this counter; guards against it reading zero
        during an apply (which would let a bench start under one)."""
        monkeypatch.setattr(settings_apply, "is_free", lambda: True)
        seen: list[int] = []

        def _apply(*_a: Any, **_k: Any) -> tuple[bool, None]:
            seen.append(settings_apply.applies_in_flight())
            return True, None

        with (
            patch("fpstune.api.routes.settings_apply.CommandExecutor.apply", _apply),
            patch("fpstune.api.routes.settings._finalize_apply_response", _finalize_stub),
        ):
            settings_apply.apply_and_finalize(_setting(), "off", MagicMock(), "Applied")
        assert seen == [1]
        assert settings_apply.applies_in_flight() == 0

    def test_counts_itself_before_it_waits_for_the_lock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Counted only after the lock looked free, an apply left a window in
        which the scheduler read zero applies and took the lock: a bench then
        measured a machine mid-apply. The scheduler must see the apply while it
        is still waiting."""
        seen_while_waiting: list[int] = []

        def _is_free() -> bool:
            seen_while_waiting.append(settings_apply.applies_in_flight())
            return True

        monkeypatch.setattr(settings_apply, "is_free", _is_free)
        with (
            patch(
                "fpstune.api.routes.settings_apply.CommandExecutor.apply",
                return_value=(True, None),
            ),
            patch("fpstune.api.routes.settings._finalize_apply_response", _finalize_stub),
        ):
            settings_apply.apply_and_finalize(_setting(), "off", MagicMock(), "Applied")
        assert seen_while_waiting == [1]
        assert settings_apply.applies_in_flight() == 0

    def test_counter_returns_to_zero_when_the_command_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings_apply, "is_free", lambda: True)
        with (
            patch(
                "fpstune.api.routes.settings_apply.CommandExecutor.apply",
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(RuntimeError),
        ):
            settings_apply.apply_and_finalize(_setting(), "off", MagicMock(), "Applied")
        assert settings_apply.applies_in_flight() == 0

    def test_two_parallel_applies_do_not_block_each_other(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bulk apply runs on several threads; a per-thread mutex here would
        serialise them. Guards against the counter being replaced by a lock."""
        monkeypatch.setattr(settings_apply, "is_free", lambda: True)
        both_inside = threading.Barrier(2, timeout=5)

        def _apply(*_a: Any, **_k: Any) -> tuple[bool, None]:
            both_inside.wait()
            return True, None

        with (
            patch("fpstune.api.routes.settings_apply.CommandExecutor.apply", _apply),
            patch("fpstune.api.routes.settings._finalize_apply_response", _finalize_stub),
        ):
            threads = [
                threading.Thread(
                    target=settings_apply.apply_and_finalize,
                    args=(_setting(), "off", MagicMock(), "Applied"),
                )
                for _ in range(2)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)
        assert not any(t.is_alive() for t in threads)


class TestStreamLeavesTheSentinel:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(create_app(), raise_server_exceptions=False)

    def _stream(self, client: TestClient, success: bool, action: str = "apply") -> MagicMock:
        setting = MagicMock()
        setting.id = "core:game_mode"
        setting.apply_type = MagicMock()
        setting.apply_type.value = "registry"
        setting.recommended_value = "1"
        setting.default_value = "0"
        setting.requires_reboot = False
        setting.apply_args = {}
        setting.display_name = "Game Mode"
        setting.duration_estimate = ""
        setting.progress_pattern = None
        response = MagicMock()
        response.success = success
        response.skipped = False
        response.error = None if success else "Access denied"
        response.new_value = "1"
        response.requires_reboot = False
        response.verified = True
        response.freed_bytes = None
        response.size_after_bytes = None
        registry = MagicMock()
        registry.get.return_value = setting
        mark = MagicMock()
        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=registry),
            patch(
                "fpstune.api.routes.settings_stream._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
            patch(
                "fpstune.api.routes.settings_stream._apply_single_setting",
                return_value=(setting, response),
            ),
            patch("fpstune.benchmark.ledger.mark_bulk_apply_finished", mark),
        ):
            r = client.post(f"/api/settings/bulk/stream-{action}", json={"ids": ["core:game_mode"]})
        assert r.status_code == 200
        return mark

    def test_successful_apply_marks_the_ledger(self, client: TestClient) -> None:
        assert self._stream(client, success=True).call_count == 1

    def test_failed_apply_does_not(self, client: TestClient) -> None:
        """Nothing changed, so there is nothing to measure after."""
        assert self._stream(client, success=False).call_count == 0

    def test_reset_does_not(self, client: TestClient) -> None:
        assert self._stream(client, success=True, action="reset").call_count == 0
