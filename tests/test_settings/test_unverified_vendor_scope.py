"""What a default scope applies must be known to work.

The AMD rows write HKCU\\SOFTWARE\\AMD\\CN, which no AMD machine has confirmed
the driver reads; in Essential and Recommended they were applied by default and
verified against the value fpstune itself had just written.
"""

from __future__ import annotations

from fpstune.settings.base import SettingScope
from fpstune.settings.definitions import gpu


def _amd_rows() -> list:
    return [
        v
        for v in vars(gpu).values()
        if isinstance(getattr(v, "id", None), str) and v.id.startswith("gpu-amd:")
    ]


def test_no_amd_registry_row_is_applied_by_default() -> None:
    rows = _amd_rows()
    assert rows, "no AMD rows found; update this guard"
    for row in rows:
        assert row.scope is SettingScope.COMPLETE, row.id


def test_hybrid_gpu_assignment_is_essential() -> None:
    # A game on the integrated chip loses more than every other tweak gains.
    assert gpu.GPU_LAPTOP_ASSIGNMENT.scope is SettingScope.ESSENTIAL
