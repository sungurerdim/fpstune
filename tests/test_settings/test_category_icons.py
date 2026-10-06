"""Every category icon the backend names is one the frontend actually ships.

The frontend used to look icons up by name in ``import * as LucideIcons``, which
kept the whole of lucide-react in the bundle (635 KB of a 1.3 MB script for a
dozen icons). It now imports each icon by name in ``lib/categoryIcons.ts``; a
category whose icon is missing there would silently fall back to the Settings
icon, so this test reads that table and holds the two sides together.
"""

from __future__ import annotations

import re
from pathlib import Path

from fpstune.settings.base import get_all_categories_metadata

ICON_TABLE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "categoryIcons.ts"


def _table_names() -> set[str]:
    source = ICON_TABLE.read_text(encoding="utf-8")
    body = re.search(r"CATEGORY_ICONS[^=]*=\s*\{(?P<body>[^}]*)\}", source)
    assert body, f"no CATEGORY_ICONS object in {ICON_TABLE}"
    return {name.strip() for name in body.group("body").split(",") if name.strip()}


def test_every_category_icon_is_in_the_frontend_table() -> None:
    named = {category.icon for category in get_all_categories_metadata()}
    missing = named - _table_names()
    assert not missing, f"add these to {ICON_TABLE.name}: {sorted(missing)}"


def test_the_table_carries_nothing_the_backend_does_not_name() -> None:
    """An unused entry is an import that only costs bytes; drop it with the category."""
    named = {category.icon for category in get_all_categories_metadata()}
    unused = _table_names() - named - {"Settings"}
    assert not unused, f"{ICON_TABLE.name} imports icons no category names: {sorted(unused)}"
