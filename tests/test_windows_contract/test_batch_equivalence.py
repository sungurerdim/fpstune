"""G4: the batch optimisation is live, and produces the same answers as off.

Twice this codebase shipped a batch that was dead in production — the adapter
snapshot that parsed to nothing (#31), and the prefetchers that copied an
empty context into their worker threads — and the suite was green both times,
because the per-setting fallback produces the same values. Only the process
count tells a live batch from a skipped one.

This runs two full detection passes against the real machine (~20 s), so it
is opt-in like the apply sweep: set FPSTUNE_BATCH_EQUIVALENCE=1. The
2026-08-26 baseline it re-proves, measured by scripts/measure_scan.py on the
dev machine: batches on = 20 processes / 413 detected; batches off = 115 /
413. Same answers, one-fifth the processes — that margin is the assertion.
Batching is disabled the same way measure_scan's --no-batch does it:
neutralise the scan cache, so every batched lookup falls back to its own
subprocess.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any
from unittest.mock import patch

import pytest

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="Runs real detection"),
    pytest.mark.skipif(
        not os.environ.get("FPSTUNE_BATCH_EQUIVALENCE"),
        reason="Set FPSTUNE_BATCH_EQUIVALENCE=1; it runs two full scans",
    ),
]


def _scan(*, use_batch: bool) -> tuple[dict[str, Any], int]:
    """One full detection pass; returns (values by id, subprocess count)."""
    from fpstune.settings.detection import DetectionEngine
    from fpstune.settings.executors import ps_batch
    from fpstune.settings.registry import SettingsRegistry

    spawned = 0
    original_popen = subprocess.Popen

    class CountingPopen(original_popen):  # type: ignore[misc,valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            nonlocal spawned
            spawned += 1
            super().__init__(*args, **kwargs)

    registry = SettingsRegistry(discover_dynamic=True)
    engine = DetectionEngine()

    patches = [patch("subprocess.Popen", CountingPopen)]
    if not use_batch:
        # measure_scan --no-batch's own mechanism, verbatim.
        patches += [
            patch.object(ps_batch, "init_scan_cache", lambda: ({}, None)),
            patch.object(ps_batch, "reset_scan_cache", lambda _token: None),
            patch.object(ps_batch, "_get_cache", lambda: None),
        ]

    from contextlib import ExitStack

    with ExitStack() as stack:
        for patcher in patches:
            stack.enter_context(patcher)
        results = engine.detect_all(registry.get_all())
    values = {r.setting_id: r.value for r in results.values() if r.value is not None}
    return values, spawned


def test_batching_changes_the_process_count_and_nothing_else() -> None:
    batched_values, batched_procs = _scan(use_batch=True)
    unbatched_values, unbatched_procs = _scan(use_batch=False)

    # Equivalence: the same machine read two ways answers the same. Volatile
    # readings (cleanup sizes mid-measure, link state) may flicker; the two
    # passes must agree on at least 95% of what both could read.
    shared = set(batched_values) & set(unbatched_values)
    agreeing = sum(1 for key in shared if batched_values[key] == unbatched_values[key])
    assert shared and agreeing / len(shared) >= 0.95, (
        f"batched and unbatched scans disagree on {len(shared) - agreeing} of "
        f"{len(shared)} shared readings"
    )

    # Liveness: a dead batch spawns as many processes as no batch at all.
    assert batched_procs * 2 < unbatched_procs, (
        f"batching spawned {batched_procs} processes vs {unbatched_procs} without — "
        "the batch is not running (baseline: 20 vs 115)"
    )
