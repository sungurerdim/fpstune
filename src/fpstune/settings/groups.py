"""Which group a setting belongs to inside the list that owns it.

A category says what kind of thing a setting is; a group says *whose* it is. The
two are different questions and the second one had no answer until now: all 181
Modern Warfare / CS2 / Heroes settings share the single category ``game_config``,
so a screen listing them could offer "Game Configs" and nothing finer. The same
held for cleanups — thirty-three actions in one flat list, a Rust registry beside
a Windows event log beside a Modern Warfare crash dump.

The label lives here rather than in the frontend because of C9: a game's display
name is already stated once, in ``game_processes.GAME_LABELS``, and a second copy
in TypeScript is the copy that goes stale. Everything a list surface renders as a
heading comes over the wire.

Membership is expressed two ways, and the difference is deliberate:

* **Derived** for anything whose id already names its owner. ``game_config:mw4:x``
  and ``game_cleanup:mw3:y`` carry the game in the id, so a new game needs no
  entry here at all — only a ``GAME_LABELS`` entry, which it needs anyway to get
  the running-game guard.
* **Declared** for cleanups, where no part of the id says whether ``cargo_cache``
  is a developer tool or a launcher. That table is a classification, not a fact
  about this machine, and ``tests/test_settings/test_groups.py`` fails the moment
  a cleanup is added without one — so the fallback is a red test, never a setting
  quietly landing in "everything else".
"""

from __future__ import annotations

from dataclasses import dataclass

from fpstune.settings.executors.game_processes import GAME_LABELS

__all__ = ["SettingGroup", "group_for"]


@dataclass(frozen=True)
class SettingGroup:
    """A heading a list surface can render, with the order it renders in."""

    id: str
    label: str
    order: int


# Games sort by the order they are declared in, ahead of every generic group, so
# a panel opens with the title the user came for rather than with shader caches.
_GAME_ORDER_BASE = 10

_GAME_GROUPS: dict[str, SettingGroup] = {
    game: SettingGroup(id=game, label=label, order=_GAME_ORDER_BASE + index)
    for index, (game, label) in enumerate(GAME_LABELS.items())
}

_WINDOWS = SettingGroup(id="windows", label="Windows", order=1)
_APPS = SettingGroup(id="apps", label="Apps & browsers", order=2)
_DEVELOPER = SettingGroup(id="developer", label="Developer caches", order=3)
_CONTAINERS = SettingGroup(id="containers", label="Containers & WSL", order=4)
_SHADER_CACHES = SettingGroup(id="shader_caches", label="Shader caches", order=20)
_LAUNCHERS = SettingGroup(id="launchers", label="Launchers & apps", order=21)

# Keyed by the part of the id after the module, because that is the part a
# cleanup owns: `cleanup:temp_files` and `game_cleanup:steam_webcache` are in
# different modules and never collide.
_CLEANUP_GROUPS: dict[str, SettingGroup] = {
    # cleanup — Windows keeps these, and only Windows writes them
    "dism_cleanup": _WINDOWS,
    "temp_files": _WINDOWS,
    "event_logs": _WINDOWS,
    "wer_reports": _WINDOWS,
    "defender_cache": _WINDOWS,
    "prefetch": _WINDOWS,
    "windows_update_cache": _WINDOWS,
    "delivery_optimization": _WINDOWS,
    "thumbnail_cache": _WINDOWS,
    "memory_dumps": _WINDOWS,
    "shadow_copy_reclaim": _WINDOWS,
    # cleanup — installed software rather than the OS
    "browser_cache": _APPS,
    # cleanup — package managers, which reclaim the most and are the safest to
    # clear: every one of them re-downloads on demand
    "pip_cache": _DEVELOPER,
    "npm_cache": _DEVELOPER,
    "yarn_cache": _DEVELOPER,
    "pnpm_cache": _DEVELOPER,
    "nuget_cache": _DEVELOPER,
    "maven_cache": _DEVELOPER,
    "gradle_cache": _DEVELOPER,
    "cargo_cache": _DEVELOPER,
    # cleanup — these shut something down to reclaim, so they group apart from
    # the ones that only delete files
    "docker_prune": _CONTAINERS,
    "docker_prune_all": _CONTAINERS,
    "wsl_compact": _CONTAINERS,
    # game_cleanup — rebuilt by the driver on the next launch
    "nvidia_shader_cache": _SHADER_CACHES,
    "amd_shader_cache": _SHADER_CACHES,
    "directx_shader_cache": _SHADER_CACHES,
    "intel_shader_cache": _SHADER_CACHES,
    # game_cleanup — the storefronts and the chat client that sits beside them
    "steam_webcache": _LAUNCHERS,
    "epic_cache": _LAUNCHERS,
    "battlenet_cache": _LAUNCHERS,
    "discord_cache": _LAUNCHERS,
    # Written by the Call of Duty launcher rather than by one title, so it groups
    # with the clients rather than under a game — two per-game entries would each
    # report freeing what the other already freed.
    "cod_crash_reports": _LAUNCHERS,
}

# The modules whose settings are grouped. Everything else is listed flat, and a
# `None` group is how a surface is told to render no heading at all.
_GROUPED_MODULES = frozenset({"game_config", "game_cleanup", "cleanup"})


def group_for(setting_id: str) -> SettingGroup | None:
    """The group a setting belongs to, or ``None`` when its list has no groups.

    Args:
        setting_id: Full setting id, e.g. ``game_config:mw4:shadow_quality``.

    Returns:
        The group, or ``None`` for a module that is not grouped or an id whose
        owner cannot be determined.
    """
    module, _, remainder = setting_id.partition(":")
    if not remainder or module not in _GROUPED_MODULES:
        return None

    # A game names itself in the id: `game_config:mw4:x`, `game_cleanup:mw3:y`.
    owner, _, rest = remainder.partition(":")
    if rest and owner in _GAME_GROUPS:
        return _GAME_GROUPS[owner]

    return _CLEANUP_GROUPS.get(remainder)
