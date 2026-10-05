"""Every setting the registry ships has Turkish copy.

The product ships to Turkish users (C4 amendment F1), and ``settingsTr.ts``
falls back to English for an id it does not know — visibly, but silently for
the author. Twenty-nine settings shipped that way before anyone counted.
Runtime-discovered rows (game titles, per-adapter network settings) depend on
the machine, so this covers the static registry; their copy is keyed by the
same ids once discovered.
"""

from __future__ import annotations

import re
from pathlib import Path

CATALOGUE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n" / "settingsTr.ts"


def _translated_ids() -> set[str]:
    return set(re.findall(r'^  "([^"]+)": \{', CATALOGUE.read_text(encoding="utf-8"), re.M))


def test_the_catalogue_is_parsed() -> None:
    # Guards the pattern itself: an empty parse would make the test below pass.
    assert len(_translated_ids()) > 300


def test_every_registered_setting_has_turkish_copy() -> None:
    from fpstune.settings.registry import SettingsRegistry

    registered = {s.id for s in SettingsRegistry(discover_dynamic=False).get_all()}
    missing = sorted(registered - _translated_ids())
    assert not missing, f"no Turkish copy in settingsTr.ts for: {missing}"
