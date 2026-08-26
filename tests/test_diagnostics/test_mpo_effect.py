"""MPO's registry value proves intent; only a capture proves effect.

The value that disables MPO changes between Windows builds, so a setting that
verifies itself by reading back what it wrote can report success while MPO is
still on. These tests pin the one distinction that separates the two, and pin
that an unanswerable capture stays unanswered rather than becoming a "no".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpstune.diagnostics.mpo_effect import read_capture, read_latest


def write_csv(path: Path, rows: list[str], header: str = "PresentMode,MsBetweenPresents") -> Path:
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


class TestReadsTheEffect:
    def test_hardware_composed_means_mpo_was_in_use(self, tmp_path: Path) -> None:
        f = write_csv(
            tmp_path / "c.csv",
            ["Hardware Composed: Independent Flip,6.9"] * 3,
        )
        obs = read_capture(f)
        assert obs.mpo_active is True
        assert obs.frames == 3
        assert "MPO was in use" in obs.summary

    def test_plain_composed_flip_means_mpo_was_not(self, tmp_path: Path) -> None:
        f = write_csv(tmp_path / "c.csv", ["Composed: Flip,6.9"] * 4)
        obs = read_capture(f)
        assert obs.mpo_active is False
        assert "not in use" in obs.summary

    def test_a_mix_counts_as_in_use(self, tmp_path: Path) -> None:
        # MPO engaging for part of a session is still MPO engaging; reporting
        # False because most frames missed it would hide the thing being hunted.
        f = write_csv(
            tmp_path / "c.csv",
            ["Composed: Flip,6.9"] * 9 + ["Hardware Composed: Independent Flip,6.9"],
        )
        obs = read_capture(f)
        assert obs.mpo_active is True
        assert obs.modes_share("hardware composed") == pytest.approx(0.1)

    def test_matching_is_case_insensitive(self, tmp_path: Path) -> None:
        # The column's spelling has changed across PresentMon versions.
        f = write_csv(tmp_path / "c.csv", ["HARDWARE COMPOSED: INDEPENDENT FLIP,6.9"])
        assert read_capture(f).mpo_active is True


class TestUnanswerableStaysUnanswered:
    def test_missing_file_is_unknown_not_false(self, tmp_path: Path) -> None:
        obs = read_capture(tmp_path / "nope.csv")
        assert obs.mpo_active is None
        assert "Not observable" in obs.summary

    def test_capture_without_the_column_is_unknown(self, tmp_path: Path) -> None:
        f = write_csv(tmp_path / "c.csv", ["6.9"], header="MsBetweenPresents")
        obs = read_capture(f)
        assert obs.mpo_active is None
        assert "PresentMode" in obs.note

    def test_empty_capture_is_unknown(self, tmp_path: Path) -> None:
        f = write_csv(tmp_path / "c.csv", [])
        assert read_capture(f).mpo_active is None

    def test_blank_present_modes_are_not_counted_as_frames(self, tmp_path: Path) -> None:
        f = write_csv(tmp_path / "c.csv", [",6.9", ",7.0"])
        assert read_capture(f).mpo_active is None


class TestLatestCapture:
    def test_no_directory_is_unknown(self, tmp_path: Path) -> None:
        assert read_latest(tmp_path / "missing").mpo_active is None

    def test_empty_directory_says_to_run_a_benchmark(self, tmp_path: Path) -> None:
        obs = read_latest(tmp_path)
        assert obs.mpo_active is None
        assert "benchmark" in obs.note

    def test_picks_the_most_recent_capture(self, tmp_path: Path) -> None:
        write_csv(tmp_path / "2026-01-01.csv", ["Composed: Flip,6.9"])
        write_csv(tmp_path / "2026-02-01.csv", ["Hardware Composed: Independent Flip,6.9"])
        assert read_latest(tmp_path).mpo_active is True
