"""The operation log: classification, one-line format, and no value history."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fpstune.utils.operation_log import (
    ADAPTER_BUSY,
    COMMAND_REJECTED,
    GAME_RUNNING,
    PARTIAL,
    PERMISSION,
    TIMEOUT,
    UNAVAILABLE,
    UNKNOWN,
    VERIFICATION_MISMATCH,
    OperationLog,
    classify_error,
    hint_for,
)


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("Access is denied", PERMISSION),
        ("İstenen kayıt defteri erişimine izin verilmiyor.", PERMISSION),
        ("Steam is running. It keeps its settings in memory.", GAME_RUNNING),
        ("network adapter 7 was not back within 30 s", ADAPTER_BUSY),
        ("Verification failed: expected 'Enabled', got 'Disabled'", VERIFICATION_MISMATCH),
        ("applied, but 2 write(s) failed", PARTIAL),
        ("Windows update is pending or installing; error 0x800f0975", "pending_update"),
        ("PowerShell failed: the command timed out", TIMEOUT),
        ("not_installed", UNAVAILABLE),
        ("Value 'Forced_Other' is not valid for this setting", COMMAND_REJECTED),
        ("", UNKNOWN),
        ("something nobody classified", UNKNOWN),
    ],
)
def test_the_classifier_names_the_actionable_cause(reason: str, expected: str) -> None:
    assert classify_error(reason) == expected


def test_every_cause_has_a_hint() -> None:
    for cause in (
        PERMISSION,
        GAME_RUNNING,
        ADAPTER_BUSY,
        VERIFICATION_MISMATCH,
        PARTIAL,
        TIMEOUT,
        UNAVAILABLE,
        COMMAND_REJECTED,
        UNKNOWN,
    ):
        assert hint_for(cause)


def _response(**overrides: object) -> SimpleNamespace:
    values = {
        "success": True,
        "error": None,
        "skipped": False,
        "verified": True,
        "requires_reboot": False,
        "freed_bytes": None,
        "state": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _setting(setting_id: str = "test:one") -> SimpleNamespace:
    return SimpleNamespace(id=setting_id)


def test_an_apply_line_is_one_readable_line_without_values(tmp_path: Path) -> None:
    log = OperationLog()
    path = log.start_session(tmp_path / "operations.log", header="test")
    log.record_apply(_setting("network:7:eee"), _response(), 1234)

    text = path.read_text(encoding="utf-8")
    assert "APPLY | ok | 1.2s | network:7:eee" in text
    assert "current=" not in text
    assert text.count("\n") == 2  # header + one operation


def test_a_failed_apply_carries_the_cause_and_a_hint(tmp_path: Path) -> None:
    log = OperationLog()
    path = log.start_session(tmp_path / "operations.log")
    log.record_apply(
        _setting("network:7:eee"),
        _response(success=False, error="Access is denied", verified=False),
        40,
    )

    text = path.read_text(encoding="utf-8")
    assert "APPLY | failed | 0.0s | network:7:eee | permission | Access is denied" in text
    assert "hint=" in text


def test_a_partial_apply_is_not_reported_as_clean_success(tmp_path: Path) -> None:
    log = OperationLog()
    path = log.start_session(tmp_path / "operations.log")
    log.record_apply(
        _setting("power:cpu_min_state"),
        _response(warnings=["applied, but 1 write(s) failed"], verified=True),
        90,
    )

    text = path.read_text(encoding="utf-8")
    assert "APPLY | partial |" in text
    assert "partial" in text


def test_a_warning_on_a_successful_apply_is_still_partial(tmp_path: Path) -> None:
    """The response now has a warnings channel; a clean `error` is not a clean run."""
    log = OperationLog()
    path = log.start_session(tmp_path / "operations.log")
    log.record_apply(
        _setting("power:cpu_min_state"),
        _response(warnings=["applied, but 1 write(s) failed"], verified=True),
        90,
    )

    text = path.read_text(encoding="utf-8")
    assert "APPLY | partial |" in text
    assert "applied, but 1 write(s) failed" in text


def test_a_skipped_setting_is_not_a_failure(tmp_path: Path) -> None:
    log = OperationLog()
    path = log.start_session(tmp_path / "operations.log")
    log.record_apply(_setting(), _response(skipped=True), 1)

    text = path.read_text(encoding="utf-8")
    assert "APPLY | skipped" in text
    assert "hint=" not in text


def test_a_scan_summary_is_one_line_with_counts(tmp_path: Path) -> None:
    log = OperationLog()
    path = log.start_session(tmp_path / "operations.log")
    log.record_detect(
        total=475,
        errors=4,
        not_applicable=61,
        optimized=363,
        not_optimized=51,
        duration_ms=36700,
    )

    text = path.read_text(encoding="utf-8")
    assert "DETECT" in text
    assert "total=475" in text
    assert "errors=4" in text
    assert "not_optimized=51" in text
    assert text.count("\n") == 2


def test_a_reason_with_newlines_and_pipes_stays_one_field(tmp_path: Path) -> None:
    log = OperationLog()
    path = log.start_session(tmp_path / "operations.log")
    log.write("apply", "failed", "test:one", reason="first\nsecond | third")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "\n" not in lines[1]
    assert "first / second / third" in lines[1]


def test_a_new_session_rotates_the_previous_file_and_keeps_five(tmp_path: Path) -> None:
    log = OperationLog()
    for index in range(7):
        path = log.start_session(tmp_path / "operations.log", header=f"run {index}")
        log.write("apply", "ok", f"test:{index}")
        # A distinct mtime per rotation, so pruning order is deterministic.
        path.touch()

    backups = sorted(tmp_path.glob("operations-*.log"))
    assert len(backups) == 5
    current = tmp_path / "operations.log"
    assert current.exists()
    assert "run 6" in current.read_text(encoding="utf-8")
