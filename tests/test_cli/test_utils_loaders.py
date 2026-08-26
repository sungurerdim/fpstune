"""The CLI's result loaders and the before/after comparison summary.

`load_*_result(name_or_path)` is the seam every compare command stands on: a
loader that returns the *first* saved result instead of the *named* one makes
every comparison silently compare the wrong runs. And the comparison summary is
the one place a regression is allowed to reach the user — celebrating a -12%
run as "no significant change" would bury exactly the signal the before/after
flow exists to surface.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpstune.commands.utils import (
    load_fps_capture,
    load_furmark_result,
    show_benchmark_comparison,
)


def _plain(text: str) -> str:
    """Rich colours 'before' inside the sentence; strip ANSI so substring
    assertions read the words, not the markup."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _result(name: str, score: int = 5000, fps_avg: float = 100.0, fps_min: float = 60.0):
    result = MagicMock()
    result.name = name
    result.score = score
    result.fps_avg = fps_avg
    result.fps_min = fps_min
    return result


class TestLoadByNameOrPath:
    def test_an_existing_path_short_circuits_the_name_search(self, tmp_path) -> None:
        saved = tmp_path / "run.json"
        saved.write_text("{}")
        fm = MagicMock()
        sentinel = _result("whatever")
        fm.load_result.return_value = sentinel

        assert load_furmark_result(fm, str(saved)) is sentinel
        fm.list_results.assert_not_called()

    def test_the_named_result_is_found_not_the_first_one(self) -> None:
        """Returning results[0] would pass every one-result test and compare
        the wrong runs the moment there are two."""
        fm = MagicMock()
        fm.list_results.return_value = ["a.json", "b.json"]
        first, wanted = _result("before"), _result("after")
        fm.load_result.side_effect = [first, wanted]

        assert load_furmark_result(fm, "after") is wanted

    def test_an_unknown_name_is_none_not_a_guess(self) -> None:
        fm = MagicMock()
        fm.list_results.return_value = ["a.json"]
        fm.load_result.return_value = _result("before")

        assert load_furmark_result(fm, "no-such-run") is None

    def test_fps_loader_has_the_same_contract(self) -> None:
        pm = MagicMock()
        pm.list_captures.return_value = [Path("x.json")]
        capture = MagicMock()
        capture.name = "match"
        pm.load_capture.return_value = capture

        assert load_fps_capture(pm, "match") is capture
        assert load_fps_capture(pm, "miss") is None


class TestComparisonSummary:
    def _fm(self, results: list, score: float = 0.0, fps: float = 0.0, low: float = 0.0):
        fm = MagicMock()
        fm.list_results.return_value = [f"{r.name}.json" for r in results]
        fm.load_result.side_effect = results
        fm.compare.return_value = MagicMock(
            score_improvement=score, fps_improvement=fps, min_fps_improvement=low
        )
        return fm

    def test_missing_before_names_the_gap_and_the_next_step(self, capsys) -> None:
        fm = self._fm([_result("after")])
        show_benchmark_comparison(fm)
        out = _plain(capsys.readouterr().out)
        assert "No 'before' benchmark" in out
        fm.compare.assert_not_called()

    def test_missing_after_points_at_the_after_flag(self, capsys) -> None:
        fm = self._fm([_result("before")])
        show_benchmark_comparison(fm)
        out = _plain(capsys.readouterr().out)
        assert "No 'after' benchmark" in out
        assert "--after" in out

    def test_a_regression_is_reported_red_with_the_way_back(self, capsys) -> None:
        """The decreased case must reach the user as a decrease and carry the
        revert hint — this is the one screen that can catch a tweak that
        lowered the ceiling (consequence 3)."""
        fm = self._fm([_result("before"), _result("after")], score=-12.0, fps=-8.0, low=-15.0)
        show_benchmark_comparison(fm)
        out = _plain(capsys.readouterr().out)
        assert "decreased" in out
        assert "revert" in out.lower()

    def test_noise_is_not_celebrated_as_a_win(self, capsys) -> None:
        fm = self._fm([_result("before"), _result("after")], score=0.0, fps=0.0, low=0.0)
        show_benchmark_comparison(fm)
        out = _plain(capsys.readouterr().out)
        assert "No significant performance change" in out

    def test_a_real_improvement_is_quantified(self, capsys) -> None:
        fm = self._fm([_result("before"), _result("after")], score=7.5, fps=6.0, low=3.0)
        show_benchmark_comparison(fm)
        out = _plain(capsys.readouterr().out)
        assert "7.5%" in out


@pytest.fixture(autouse=True)
def _wide_console(monkeypatch):
    """Rich truncates table cells at narrow widths; pin the width so asserted
    substrings cannot be cut mid-word by the CI terminal."""
    monkeypatch.setenv("COLUMNS", "200")
