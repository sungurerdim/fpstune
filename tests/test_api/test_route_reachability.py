"""A registered route is called by the UI, on the baseline, or deleted.

The defect this file exists for: 38 of 71 routes had no caller — whole
surfaces (GPU, display/VRR, power profiles) existed only as endpoints, and
`GET /settings/actions/{id}/execute`'s one caller was itself an orphaned
component. Dead routes read as capabilities and rot as attack surface; a
route nobody calls is either wired or removed (breaking-first).

The baseline below froze the orphan set the D-epic inherited. It may only
shrink: a new uncalled route fails immediately, and an entry that gains a
caller (or is deleted) turns stale and must be removed here in the same
change, so the shrink is visible in the diff.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.routing import APIRoute

from fpstune.api.main import create_app

ROOT = Path(__file__).resolve().parents[2]

# Frozen at the D7 audit. Entries leave this set by gaining a caller or by
# being deleted — never by growing the set.
_UNCALLED_BASELINE = {
    "GET /api/benchmark/compare",
    "GET /api/benchmark/results",
    "GET /api/benchmark/results/{result_name}",
    "GET /api/display/monitors",
    "GET /api/display/vrr-optimization",
    "GET /api/gpu",
    "GET /api/gpu/detect",
    "GET /api/gpu/settings",
    "GET /api/hardware/context",
    "GET /api/network/adapter/{adapter_name}/status",
    "GET /api/power-profile/status",
    "GET /api/self-check",
    "GET /api/settings/categories/{category_id}/metadata",
    "GET /api/settings/count",
    "GET /api/settings/definitions/category/{category}",
    "GET /api/settings/detect/{setting_id}",
    "GET /api/settings/modules/{module_id}/metadata",
    "POST /api/benchmark/baseline",
    "POST /api/benchmark/start",
    "POST /api/display/vrr-optimization/apply",
    "POST /api/display/vrr-optimization/reset",
    "POST /api/elevate",
    "POST /api/gpu/amd/apply",
    "POST /api/gpu/apply",
    "POST /api/gpu/nvidia/apply",
    "POST /api/power-profile/activate",
    "POST /api/power-profile/revert",
    "POST /api/restore-point",
    "POST /api/settings/bulk/optimize",
    "POST /api/settings/bulk/reset",
    "POST /api/settings/game-configs/sweep",
    "POST /api/settings/{setting_id}/reset",
    "POST /api/settings/{setting_id}/revert",
    "POST /api/settings/{setting_id}/verify",
}


def _frontend_source() -> str:
    chunks = []
    for path in (ROOT / "frontend" / "src").rglob("*"):
        if (
            path.suffix in (".ts", ".tsx")
            and ".test." not in path.name
            and "__tests__" not in path.parts
        ):
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _uncalled_routes() -> set[str]:
    frontend = _frontend_source()
    uncalled: set[str] = set()
    for route in create_app().routes:
        if not isinstance(route, APIRoute):
            continue
        # The frontend's fetch helper supplies the /api prefix.
        short = route.path.removeprefix("/api")
        pattern = re.escape(re.sub(r"\{[^}]+\}", "@@", short)).replace("@@", r"[^\"`]*?")
        if re.search(pattern, frontend) is None:
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                uncalled.add(f"{method} {route.path}")
    return uncalled


class TestEveryRouteHasACallerOrAVerdict:
    def test_no_route_outside_the_frozen_baseline_is_uncalled(self) -> None:
        new_orphans = sorted(_uncalled_routes() - _UNCALLED_BASELINE)
        assert not new_orphans, (
            "routes with no UI caller and no baseline verdict — wire them or "
            f"delete them: {new_orphans}"
        )

    def test_the_baseline_only_shrinks(self) -> None:
        stale = sorted(_UNCALLED_BASELINE - _uncalled_routes())
        assert not stale, (
            "baseline entries that gained a caller or were deleted — remove "
            f"them from _UNCALLED_BASELINE so the shrink is on the record: {stale}"
        )
