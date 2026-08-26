"""The one result store every bench writes through (issue #20, issue #24).

Five benches carried a byte-identical save/load/list trio, and the traversal fix
landed in one of them: `runner.py` squashed a result name into a safe filename
component while `dpc`, `network`, `furmark` and `presentmon` still let it become
a path. Extracting the store is what makes one sanitiser cover all five, so the
boundary set is asserted here once and the benches are asserted to use it.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest

from fpstune.benchmark.result_store import ResultStore, safe_filename_component


@pytest.fixture
def store(tmp_path: Path) -> ResultStore:
    return ResultStore(tmp_path, logging.getLogger("result_store_under_test"))


class TestNameSanitization:
    @pytest.mark.parametrize(
        "hostile",
        [
            "..\\..\\evil",
            "../../../etc/passwd",
            "C:\\Windows\\System32\\evil",
            "\\\\server\\share\\evil",
            "..",
            "...",
            ".",
            "",
            "   ",
            'a/b\\c:d*e?"f<g>h|i',
            "name\nwith\nnewlines",
            "x" * 500,
        ],
    )
    def test_a_hostile_name_stays_one_component_inside_the_directory(
        self, store: ResultStore, tmp_path: Path, hostile: str
    ) -> None:
        path = store.save({"name": hostile}, hostile)

        assert path.parent == tmp_path.resolve()
        assert path.exists()
        assert path.suffix == ".json"

    @pytest.mark.parametrize(
        "reserved",
        ["CON", "PRN", "AUX", "NUL", "COM1", "LPT9", "con", "nul.json"],
    )
    def test_a_reserved_device_name_never_becomes_the_component(self, reserved: str) -> None:
        """Win32 resolves these as devices whatever directory they sit in, so a
        component that is safe only because its caller appends a timestamp is
        not a safe component."""
        component = safe_filename_component(reserved)

        assert component.split(".", 1)[0].upper() not in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "LPT9",
        }

    def test_the_component_is_bounded(self) -> None:
        assert len(safe_filename_component("x" * 500)) == 64

    def test_a_name_that_reduces_to_nothing_falls_back(self) -> None:
        assert safe_filename_component("...") == "benchmark"
        assert safe_filename_component("") == "benchmark"

    def test_separators_collapse_rather_than_multiply(self) -> None:
        assert safe_filename_component('a/b\\c:d*e?"f') == "a_b_c_d_e_f"

    def test_several_parts_join_into_one_component(self) -> None:
        """PresentMon names a capture after the run *and* the detected game."""
        assert safe_filename_component("before", "Some Game") == "before_Some_Game"

    def test_unicode_is_squashed_rather_than_passed_through(self) -> None:
        assert safe_filename_component("有効") == "benchmark"
        assert safe_filename_component("run-有効") == "run-"


class TestSaveLoadRoundTrip:
    def test_a_saved_payload_reads_back_unchanged(self, store: ResultStore) -> None:
        payload = {"name": "before", "metrics": {"fps_avg": 143.25}, "notes": ""}

        path = store.save(payload, "before")
        loaded = store.load(path, lambda data: data)

        assert loaded == payload

    def test_the_file_is_json_a_person_can_read(self, store: ResultStore) -> None:
        path = store.save({"name": "before"}, "before")
        assert json.loads(path.read_text(encoding="utf-8")) == {"name": "before"}

    def test_an_unreadable_result_says_so_rather_than_vanishing(
        self, store: ResultStore, tmp_path: Path, caplog
    ) -> None:
        """C11 rule 3: a measurement that cannot be read back names its reason.
        `runner.py` used to swallow this one in silence."""
        broken = tmp_path / "broken.json"
        broken.write_text("not valid json", encoding="utf-8")

        with caplog.at_level(logging.ERROR):
            assert store.load(broken, lambda data: data) is None

        assert "broken.json" in caplog.text

    def test_a_missing_file_is_reported_not_raised(
        self, store: ResultStore, tmp_path: Path
    ) -> None:
        assert store.load(tmp_path / "absent.json", lambda data: data) is None

    def test_a_json_document_that_is_not_an_object_is_refused(
        self, store: ResultStore, tmp_path: Path
    ) -> None:
        listy = tmp_path / "listy.json"
        listy.write_text("[1, 2, 3]", encoding="utf-8")

        assert store.load(listy, lambda data: data) is None

    def test_a_missing_required_key_is_reported_not_raised(
        self, store: ResultStore, tmp_path: Path
    ) -> None:
        partial = tmp_path / "partial.json"
        partial.write_text(json.dumps({"timestamp": "2026-08-25T12:00:00"}), encoding="utf-8")

        assert store.load(partial, lambda data: data["name"]) is None


class TestListing:
    def test_results_are_listed_newest_first_by_modification_time(
        self, store: ResultStore, tmp_path: Path
    ) -> None:
        """Filenames only order results that share a prefix, so a directory
        holding two differently named benches sorted alphabetically and called
        it recency."""
        older = tmp_path / "zulu_20260101_000000.json"
        older.write_text("{}", encoding="utf-8")
        time.sleep(0.05)
        newer = tmp_path / "alpha_20260101_000001.json"
        newer.write_text("{}", encoding="utf-8")

        assert store.list_files() == [newer, older]

    def test_an_empty_directory_lists_nothing(self, store: ResultStore) -> None:
        assert store.list_files() == []

    def test_a_directory_that_does_not_exist_lists_nothing(self, tmp_path: Path) -> None:
        store = ResultStore(tmp_path / "absent", logging.getLogger("result_store_under_test"))
        assert store.list_files() == []


class TestEveryBenchUsesTheStore:
    """The point of extracting it: the sanitiser applies to all five at once."""

    def test_dpc_squashes_a_traversal_name(self, tmp_path: Path) -> None:
        from fpstune.benchmark.dpc import DpcBenchmark, DpcBenchmarkResult, DpcStats

        bench = DpcBenchmark(results_dir=tmp_path)
        result = DpcBenchmarkResult(
            name="..\\..\\evil",
            timestamp="2026-08-25T12:00:00",
            stats=DpcStats(),
        )

        path = bench.save_result(result)

        assert path.parent == tmp_path.resolve()
        assert "evil" in path.name

    def test_network_squashes_a_traversal_name(self, tmp_path: Path) -> None:
        from fpstune.benchmark.network import (
            LatencyStats,
            NetworkBenchmark,
            NetworkBenchmarkResult,
        )

        bench = NetworkBenchmark(results_dir=tmp_path)
        result = NetworkBenchmarkResult(
            name="../../evil",
            timestamp="2026-08-25T12:00:00",
            target="8.8.8.8",
            stats=LatencyStats(),
        )

        path = bench.save_result(result)

        assert path.parent == tmp_path.resolve()
        assert "evil" in path.name

    def test_furmark_squashes_a_traversal_name(self, tmp_path: Path) -> None:
        from fpstune.benchmark.furmark import FurMarkBenchmark, FurMarkResult

        bench = FurMarkBenchmark(data_dir=tmp_path)
        result = FurMarkResult(
            name="..\\..\\evil",
            timestamp="2026-08-25T12:00:00",
            duration_seconds=60,
        )

        path = bench.save_result(result)

        assert path.parent == (tmp_path / "results").resolve()
        assert "evil" in path.name

    def test_presentmon_squashes_both_halves_of_a_capture_name(self, tmp_path: Path) -> None:
        from fpstune.benchmark.presentmon import (
            BenchmarkCapture,
            FrameTimeStats,
            PresentMonBenchmark,
        )

        bench = PresentMonBenchmark(data_dir=tmp_path)
        capture = BenchmarkCapture(
            name="..\\..\\before",
            timestamp="2026-08-25T12:00:00",
            game_name="../../Some Game",
            stats=FrameTimeStats(),
        )

        path = bench.save_capture(capture)

        assert path.parent == tmp_path.resolve()
        assert "before" in path.name
        assert "Game" in path.name

    def test_runner_squashes_a_traversal_name(self, tmp_path: Path) -> None:
        from fpstune.benchmark.runner import BenchmarkResult, BenchmarkRunner

        runner = BenchmarkRunner(output_dir=tmp_path)
        path = runner.save_result(BenchmarkResult(timestamp="2026-08-25T12:00:00", name="../evil"))

        assert path.parent == tmp_path.resolve()
        assert "evil" in path.name
