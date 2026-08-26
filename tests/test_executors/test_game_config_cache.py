"""Tests for the per-scan game config file cache.

47 MW3 settings share one options file and 24 CS2 settings share one
autoexec.cfg. Each used to spawn its own PowerShell process, so the batch has
to reproduce the exact semantics those commands had — especially the three
distinct CS2 states, which are easy to collapse by accident.
"""

from __future__ import annotations

import pytest

from fpstune.settings.executors import game_config_cache as gcc
from fpstune.settings.executors.ps_batch import init_scan_cache, reset_scan_cache

MW3_SAMPLE = """
// System
VSync:0.0 = "false"
RendererWorkerCount:0.0 = "7" // -1 to 16
DLSSMode:1.1 = "quality"
VideoMemoryScale:0.0 = "0.800000"
"""

CS2_SAMPLE = """
// ===fpstune-fps_max-start===
fps_max 0
// ===fpstune-fps_max-end===
// ===fpstune-cs2_rate-start===
rate 786432
// ===fpstune-cs2_rate-end===
"""


@pytest.fixture
def scan_cache():
    """Every scan gets a fresh cache, so no run can read another run's state."""
    _, token = init_scan_cache()
    yield
    reset_scan_cache(token)


def _seed(monkeypatch, *, mw3=None, cs2=None, cs2_installed=False):
    monkeypatch.setattr(
        gcc,
        "_load_snapshot",
        lambda: {"mw3": mw3, "cs2": cs2, "cs2_installed": cs2_installed},
    )


@pytest.mark.usefixtures("scan_cache")
class TestMw3Options:
    def test_reads_declared_key(self, monkeypatch):
        _seed(monkeypatch, mw3=MW3_SAMPLE)
        assert gcc.get_mw3_option("VSync") == "false"

    def test_key_with_different_version_suffix(self, monkeypatch):
        """The numeric suffix varies per key (0.0, 1.1) and must not be matched
        literally."""
        _seed(monkeypatch, mw3=MW3_SAMPLE)
        assert gcc.get_mw3_option("DLSSMode") == "quality"

    def test_value_with_trailing_comment(self, monkeypatch):
        _seed(monkeypatch, mw3=MW3_SAMPLE)
        assert gcc.get_mw3_option("RendererWorkerCount") == "7"

    def test_missing_key_reports_not_installed(self, monkeypatch):
        _seed(monkeypatch, mw3=MW3_SAMPLE)
        assert gcc.get_mw3_option("NoSuchSetting") == gcc.NOT_INSTALLED

    def test_absent_file_reports_not_installed(self, monkeypatch):
        _seed(monkeypatch, mw3=None)
        assert gcc.get_mw3_option("VSync") == gcc.NOT_INSTALLED

    def test_key_is_not_matched_as_substring(self, monkeypatch):
        """'Sync' must not match the 'VSync' line."""
        _seed(monkeypatch, mw3=MW3_SAMPLE)
        assert gcc.get_mw3_option("Sync") == gcc.NOT_INSTALLED


@pytest.mark.usefixtures("scan_cache")
class TestCs2Markers:
    def test_present_marker(self, monkeypatch):
        _seed(monkeypatch, cs2=CS2_SAMPLE, cs2_installed=True)
        assert gcc.get_cs2_marker("fps_max", "uncapped", "default") == "uncapped"

    def test_absent_marker(self, monkeypatch):
        _seed(monkeypatch, cs2=CS2_SAMPLE, cs2_installed=True)
        assert gcc.get_cs2_marker("cs2_sdr", "enabled", "default") == "default"

    def test_installed_without_autoexec_is_absent_not_missing(self, monkeypatch):
        """CS2 present but no autoexec.cfg means 'nothing managed yet' — the
        original command returned the absent value here, not 'not_installed'."""
        _seed(monkeypatch, cs2=None, cs2_installed=True)
        assert gcc.get_cs2_marker("fps_max", "uncapped", "default") == "default"

    def test_game_not_installed_reports_not_installed(self, monkeypatch):
        _seed(monkeypatch, cs2=None, cs2_installed=False)
        assert gcc.get_cs2_marker("fps_max", "uncapped", "default") == gcc.NOT_INSTALLED

    def test_non_default_absent_value_is_honoured(self, monkeypatch):
        """dynamic_lighting uses enabled/disabled, not optimized/default."""
        _seed(monkeypatch, cs2=CS2_SAMPLE, cs2_installed=True)
        assert gcc.get_cs2_marker("dynamic_lighting", "disabled", "enabled") == "enabled"


@pytest.mark.usefixtures("scan_cache")
class TestSnapshotIsReadOncePerScan:
    def test_file_is_loaded_only_once_within_a_scan(self, monkeypatch):
        calls = {"n": 0}

        def counting_load():
            calls["n"] += 1
            return {"mw3": MW3_SAMPLE, "cs2": None, "cs2_installed": False}

        monkeypatch.setattr(gcc, "_load_snapshot", counting_load)

        for _ in range(10):
            gcc.get_mw3_option("VSync")

        assert calls["n"] == 1

    def test_each_scan_starts_from_a_fresh_cache(self, monkeypatch):
        """A later scan must never serve the earlier scan's file contents."""
        _, token = init_scan_cache()
        monkeypatch.setattr(
            gcc, "_load_snapshot", lambda: {"mw3": MW3_SAMPLE, "cs2": None, "cs2_installed": False}
        )
        assert gcc.get_mw3_option("VSync") == "false"
        reset_scan_cache(token)

        _, token2 = init_scan_cache()
        monkeypatch.setattr(
            gcc, "_load_snapshot", lambda: {"mw3": None, "cs2": None, "cs2_installed": False}
        )
        assert gcc.get_mw3_option("VSync") == gcc.NOT_INSTALLED
        reset_scan_cache(token2)
