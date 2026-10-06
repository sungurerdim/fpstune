"""Every row says whose stock its default is, and that default is a value it can hold.

C6 makes reset one thing: write ``default_value``. That only works when the value
is a domain's own stock. The defect class (#104, eleven fixes: cpu_epp 50 taken
from a Server tuning document, the battery default written onto mains, an MSI key
deleted instead of set to the driver's INF value, NIC keywords reset to a
remembered constant) is one shape: a default that nobody derived. This gate holds
the whole registry, and every per-adapter / per-game row a factory builds, to
three things:

1. a row names its ``DefaultSource``, and the name agrees with the markers the row
   already carries (a powercfg row is a scheme default, a game-config row a game
   default, a hardware component's row a driver default);
2. ``default_value`` is a value the row can hold: present unless the source is
   ``NONE``, inside ``choices``, inside ``min_value``/``max_value``, never an
   absence sentinel;
3. a scheme default is adopted from the machine at build time: it follows what
   ``DefaultPowerSchemeValues`` publishes instead of staying a curated constant.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from fpstune.settings.applicability import is_absent_reading, values_equal
from fpstune.settings.base import (
    DefaultSource,
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.definitions.power import adopt_windows_defaults
from fpstune.settings.executors import map_raw_to_display
from fpstune.settings.registry import SettingsRegistry

# Definitions files whose factories build per-adapter, per-panel and per-game rows
# at discovery time; none of them is in the static registry.
_FACTORY_MODULES = (
    "display",
    "game_configs",
    "game_configs_mw4",
    "game_configs_titles",
    "gpu",
    "network",
)

# Sample inputs for a factory's parameters, by name. A factory asking for a
# parameter not listed here is skipped, and `test_the_factory_sweep_is_not_vacuous`
# fails when too few were reachable.
_FACTORY_ARGS: dict[str, Any] = {
    "interface_index": 7,
    "display_name": "Ethernet",
    "max_hz": 240,
    "vrr": True,
    "vrr_available": True,
    "build": 26100,
    "width": 2560,
    "height": 1440,
    "gpu_vendor": "nvidia",
    "vram_mb": 8192,
    "device_hz": 48000,
    "monitor_label": "Panel",
}

# Rows (static or factory-built) found violating, whose definitions file is owned
# by another change right now. Shrink-only: `test_the_pending_set_only_shrinks`
# fails the moment one is fixed, so the entry has to be deleted with the fix.
_PENDING: frozenset[str] = frozenset()


def _factory_rows() -> list[SettingExecutor]:
    rows: list[SettingExecutor] = []
    for module_name in _FACTORY_MODULES:
        module = importlib.import_module(f"fpstune.settings.definitions.{module_name}")
        for name, factory in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("create_") or factory.__module__ != module.__name__:
                continue
            kwargs: dict[str, Any] = {}
            for parameter in inspect.signature(factory).parameters.values():
                if parameter.name in _FACTORY_ARGS:
                    kwargs[parameter.name] = _FACTORY_ARGS[parameter.name]
                elif parameter.default is inspect.Parameter.empty:
                    break
            else:
                built = factory(**kwargs)
                if isinstance(built, SettingExecutor):
                    rows.append(built)
    return rows


def _in_range(setting: SettingExecutor) -> bool:
    value = setting.default_value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    if setting.min_value is not None and value < setting.min_value:
        return False
    return setting.max_value is None or value <= setting.max_value


def violations(settings: list[SettingExecutor]) -> dict[str, str]:
    """Row id -> what is wrong with its default, for every row that has a reset."""
    found: dict[str, str] = {}
    for s in settings:
        if s.is_action or s.is_readonly:
            continue
        source = s.default_source
        if source is None:
            found[s.id] = "names no default source"
        elif (source is DefaultSource.NONE) != (s.default_value is None):
            found[s.id] = f"source {source} but default_value={s.default_value!r}"
        elif source is DefaultSource.SCHEME and s.detect_type is not DetectType.POWERCFG:
            found[s.id] = "scheme default on a row powercfg does not read"
        elif s.detect_type is DetectType.POWERCFG and source is not DefaultSource.SCHEME:
            found[s.id] = f"powercfg row with a {source} default"
        elif source is DefaultSource.GAME and s.module != "game_config":
            found[s.id] = "game default on a row outside game_config"
        elif s.module == "game_config" and source is not DefaultSource.GAME:
            found[s.id] = f"game-config row with a {source} default"
        elif source is DefaultSource.DRIVER and s.component is None:
            found[s.id] = "driver default on a row with no hardware component"
        elif s.default_value is None:
            continue
        elif isinstance(s.default_value, str) and is_absent_reading(s.default_value):
            found[s.id] = f"default is the absence sentinel {s.default_value!r}"
        elif s.value_type is SettingValueType.CHOICE and not any(
            values_equal(s.default_value, choice) for choice in s.choices
        ):
            found[s.id] = f"default {s.default_value!r} is not one of {s.choices}"
        elif not _in_range(s):
            found[s.id] = f"default {s.default_value!r} outside {s.min_value}..{s.max_value}"
    return found


@pytest.fixture(scope="module")
def static_rows() -> list[SettingExecutor]:
    return SettingsRegistry(discover_dynamic=False).get_all()


@pytest.fixture(scope="module")
def factory_rows() -> list[SettingExecutor]:
    return _factory_rows()


def test_every_registered_row_has_a_derivable_default(static_rows: list[SettingExecutor]) -> None:
    found = {k: v for k, v in violations(static_rows).items() if k not in _PENDING}
    assert found == {}


def test_every_factory_built_row_has_a_derivable_default(
    factory_rows: list[SettingExecutor],
) -> None:
    found = {k: v for k, v in violations(factory_rows).items() if k not in _PENDING}
    assert found == {}


def test_the_pending_set_only_shrinks(
    static_rows: list[SettingExecutor], factory_rows: list[SettingExecutor]
) -> None:
    still_wrong = violations(static_rows) | violations(factory_rows)
    fixed = sorted(_PENDING - still_wrong.keys())
    assert fixed == [], f"fixed, delete from _PENDING: {fixed}"


def test_the_factory_sweep_is_not_vacuous(factory_rows: list[SettingExecutor]) -> None:
    # 42 factories were reachable when this gate was written; a refactor of the
    # argument names that silently halves the sweep must fail here, not pass.
    assert len(factory_rows) >= 35
    assert any(s.module == "network" for s in factory_rows)


def _sample(**overrides: Any) -> SettingExecutor:
    fields: dict[str, Any] = {
        "id": "perf:sample",
        "category": SettingCategory.CORE,
        "display_name": "Sample",
        "description": "Sample row.",
        "choices": ("off", "on"),
        "default_value": "off",
    }
    return SettingExecutor(**(fields | overrides))


def test_a_row_that_names_no_source_gets_one_from_its_own_markers() -> None:
    assert _sample().default_source is DefaultSource.WINDOWS_STOCK
    assert _sample(detect_type=DetectType.POWERCFG).default_source is DefaultSource.SCHEME
    assert _sample(id="game_config:cs2:x").default_source is DefaultSource.GAME
    assert _sample(component="gpu").default_source is DefaultSource.DRIVER
    explicit = _sample(default_source=DefaultSource.NONE, default_value=None)
    assert explicit.default_source is DefaultSource.NONE


@pytest.mark.parametrize(
    ("row", "needle"),
    [
        (_sample(default_value=None), "source"),
        (_sample(default_value="auto"), "not one of"),
        (_sample(default_value="not_supported"), "sentinel"),
        (_sample(default_source=DefaultSource.NONE), "source"),
        (
            _sample(
                value_type=SettingValueType.INT,
                choices=(),
                default_value=4000,
                min_value=0,
                max_value=1000,
            ),
            "outside",
        ),
        (_sample(default_source=DefaultSource.SCHEME), "powercfg"),
        (_sample(default_source=DefaultSource.GAME), "game_config"),
        (
            _sample(detect_type=DetectType.POWERCFG, default_source=DefaultSource.WINDOWS_STOCK),
            "powercfg",
        ),
        (_sample(id="game_config:cs2:x", default_source=DefaultSource.DRIVER), "game-config"),
        (_sample(default_source=DefaultSource.DRIVER), "no hardware component"),
    ],
)
def test_the_gate_names_each_way_a_default_can_be_wrong(row: SettingExecutor, needle: str) -> None:
    """Red proof: each defect the class shipped is reported, with the row's id."""
    found = violations([row])
    assert row.id in found
    assert needle in found[row.id]


def _publishes(raw: int) -> Callable[[str, str], int | None]:
    def reader(_subgroup: str, _guid: str) -> int | None:
        return raw

    return reader


def test_a_scheme_default_follows_what_windows_publishes(
    static_rows: list[SettingExecutor],
) -> None:
    """The adoption is the derivation: a constant surviving it is the defect.

    Each powercfg row is adopted from a reader that answers a raw value other than
    the one it carries, on a copy; the copy must now carry that value's display
    form. A row that stays put is a curated constant no machine ever overrides.
    """
    scheme_rows = [s for s in static_rows if s.default_source is DefaultSource.SCHEME]
    assert len(scheme_rows) >= 20
    stuck: list[str] = []
    for setting in scheme_rows:
        carried = setting.default_value
        other = next(
            (
                raw
                for raw in setting.value_map
                if isinstance(raw, int)
                and not values_equal(map_raw_to_display(setting.value_map, raw), carried)
            ),
            None,
        )
        if other is None:
            continue
        copy = replace(setting)
        adopt_windows_defaults([copy], reader=_publishes(other))
        if not values_equal(copy.default_value, map_raw_to_display(setting.value_map, other)):
            stuck.append(setting.id)
    assert stuck == []
