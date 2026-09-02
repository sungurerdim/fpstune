"""The settings this machine has, derived from the machine.

A discoverer is a producer: it reads what the hardware says about itself and
registers the settings that reading justifies. It is not a method on the
registry, and that is the point — a registry method can reach into
``_settings``, while a discoverer is handed the :class:`Registrar` protocol
below and can do exactly three things through it. Adding a game therefore means
adding one module and one entry to :data:`DISCOVERERS`, not editing the class
that also decides how network adapters are enumerated.

The order in :data:`DISCOVERERS` is load-bearing and each entry says why.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor
    from fpstune.settings.discovery.probes import HardwareProbes


class Registrar(Protocol):
    """What a discoverer is allowed to do to the registry.

    Deliberately three methods. ``register`` replaces by id, which is how a pass
    that re-values a setting another pass already registered does its work —
    there is no separate mutate, and no discoverer holds the settings dict.
    """

    def register(self, setting: SettingExecutor) -> None: ...

    def get(self, setting_id: str) -> SettingExecutor | None: ...

    def get_all(self) -> list[SettingExecutor]: ...


Discoverer = Callable[["Registrar", "HardwareProbes"], int]


def all_discoverers() -> tuple[Discoverer, ...]:
    """Every discovery pass, in the order the registry must run them.

    Imported lazily because each pass imports the definitions it registers, and
    those import back into ``settings`` — the same reason the registry itself
    imports its definitions inside a function.
    """
    from fpstune.settings.discovery.display import (
        discover_mpo_setting,
        discover_vrr_dependent_settings,
    )
    from fpstune.settings.discovery.games_hots import (
        discover_hots_audio_settings,
        discover_hots_display_settings,
    )
    from fpstune.settings.discovery.games_mw3 import discover_mw3_display_settings
    from fpstune.settings.discovery.games_mw4 import (
        adopt_mw4_ranges,
        discover_mw4_display_settings,
    )
    from fpstune.settings.discovery.headroom import apply_headroom_bands
    from fpstune.settings.discovery.network import (
        discover_network_adapter_settings,
        discover_wifi_link_quality,
    )

    return (
        discover_network_adapter_settings,
        # Reads the adapter list the pass above memoised; one advisory per radio.
        discover_wifi_link_quality,
        discover_mpo_setting,
        discover_mw3_display_settings,
        discover_mw4_display_settings,
        # After the derived settings are registered, so their ranges come from
        # the file too rather than from the literals the factories carry.
        adopt_mw4_ranges,
        # Last of the MW passes: it re-scopes and re-values settings the two
        # above replaced.
        apply_headroom_bands,
        discover_hots_display_settings,
        discover_hots_audio_settings,
        discover_vrr_dependent_settings,
    )


__all__ = ["Discoverer", "Registrar", "all_discoverers"]
