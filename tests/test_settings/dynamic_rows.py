"""Every row the registry can hold: the static ones, and the ones built for a machine.

Per-adapter, per-game and per-panel rows are built at run time by the ``create_*`` factories
in ``settings.definitions`` from what the hardware reports, so no static list holds them. A
test that reads only ``get_all_static_settings()`` never sees their copy or their scores. This
module builds them from a fixture context: one reading of each factory argument, or several
where the row's copy forks on it (a vendor, a refresh rate, a panel that does or does not do
VRR). Every figure is a stand-in for what hardware would report, never a real machine's (C9).

A factory with an argument that has no reading in ``FIXTURE_READINGS`` fails
``test_copy_claims.py::test_every_factory_argument_has_a_fixture_reading`` by name, so a new
factory cannot ship outside the scans that use this module.
"""

from __future__ import annotations

import importlib
import inspect
import itertools
import pkgutil
import re
from collections.abc import Callable
from types import ModuleType
from typing import Any

from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions import get_all_static_settings

FIXTURE_READINGS: dict[str, tuple[Any, ...]] = {
    "interface_index": (7,),
    "display_name": ("Test adapter",),
    "interface_guid": ("{test-guid}",),
    "path_mtu": (1500, 1280),
    "queue_counts": (("1", "2", "4", "8"),),
    "driver_default": ("4",),
    "target_core": (2,),
    "build": (22631, 26200),
    "device_hz": (44100, 48000, 96000),
    "gpu_vendor": ("nvidia", "amd", "intel"),
    "vram_mb": (4096, 8192, 24576),
    "width": (1920, 3840),
    "height": (1080, 2160),
    "max_hz": (60, 144, 240, 360),
    "vrr": (True, False),
    "vrr_available": (True, False),
    "monitor_label": ("Test panel",),
    "key": ("TEST1234",),
    "subject": ("Test panel",),
    "primary": (True, False),
    "refresh_hz": (60, 144),
    "max_refresh_hz": (144, 240),
}


def _definition_modules() -> list[ModuleType]:
    """Every module of ``settings.definitions``: where the static rows and the factories live."""
    from fpstune.settings import definitions

    return [
        importlib.import_module(info.name)
        for info in pkgutil.iter_modules(definitions.__path__, f"{definitions.__name__}.")
    ]


def factories() -> dict[str, Callable[..., SettingExecutor]]:
    """Every ``create_*`` factory a discovery pass calls to build a row for this machine."""
    return {
        f"{module.__name__}.{name}": factory
        for module in _definition_modules()
        for name, factory in vars(module).items()
        if name.startswith("create_")
        and inspect.isfunction(factory)
        and factory.__module__ == module.__name__
    }


def factory_settings() -> list[SettingExecutor]:
    """The rows the dynamic passes build, one per fixture reading of each factory's arguments."""
    rows: list[SettingExecutor] = []
    for factory in factories().values():
        names = [
            name
            for name, p in inspect.signature(factory).parameters.items()
            if name in FIXTURE_READINGS or p.default is inspect.Parameter.empty
        ]
        readings = itertools.product(*(FIXTURE_READINGS[name] for name in names))
        rows += [factory(**dict(zip(names, reading, strict=True))) for reading in readings]
    return rows


def all_settings() -> list[SettingExecutor]:
    """Static rows first, then the factory-built ones."""
    return [*get_all_static_settings(), *factory_settings()]


def id_key(setting_id: str) -> str:
    """A dynamic id carries a machine's own index or key; a record names the pattern (C9)."""
    return re.sub(r"^(network):[^:]+:|^(display):[^:]+:", r"\1\2:*:", setting_id)
