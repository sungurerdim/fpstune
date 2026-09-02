"""What on this machine would stop working if virtualization were switched off.

Two settings turn the platform off — ``system:hyper_v`` and
``system:vm_platform`` — and both used to be gated on a single hardcoded path::

    _DOCKER_DESKTOP = r"C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"

That is the C9 bug in its purest form, and it shipped. Docker Desktop moved to a
per-user install (``%LOCALAPPDATA%\\Programs\\DockerDesktop``), so on a machine
running Docker 29.7.2 the check answered "no Docker" and fpstune recommended
disabling the platform Docker runs on. The same wrong answer hid
``cleanup:docker_prune`` from the one user who had something to prune.

So this module discovers consumers instead of asserting where they live, and it
answers with **names rather than a boolean**. A user who is told "this disables
Hyper-V" cannot judge the trade; a user told "Docker Desktop and 2 WSL
distributions run on this" can. That is the whole reason each consumer carries a
``label`` and the evidence that found it.

Nothing here runs a subprocess. Registry reads and path checks answer the same
question that ``wsl.exe --list`` and ``docker info`` would, without paying a
process per scan (C7) — and they answer it for a stopped service too, which the
CLI probes do not.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from fpstune.utils.logger import get_logger

logger = get_logger()


@dataclass(frozen=True)
class VirtualizationConsumer:
    """One installed thing that needs the virtualization platform.

    ``key`` is what ``applicable_conditions`` matches on; ``label`` is what the
    user reads in the confirmation before turning the platform off.
    """

    key: str
    label: str
    evidence: str


# Docker Desktop registers an uninstall entry wherever it installs itself, under
# HKLM for a machine-wide install and HKCU for the per-user one that is now the
# default. Reading the entry rather than guessing a path is what makes this
# survive the next time the installer moves.
_DOCKER_UNINSTALL_KEYS = (
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop", "HKLM"),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\DockerDesktop", "HKLM"),
    (r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop", "HKCU"),
    (r"Software\Microsoft\Windows\CurrentVersion\Uninstall\DockerDesktop", "HKCU"),
)

# Every installed WSL distribution registers itself here, whether or not it has
# ever been started. `DefaultDistribution` alone is not enough — it survives an
# uninstall of the last distribution on some builds.
_WSL_DISTRIBUTIONS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Lxss"


def _registry_key_exists(root: str, path: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        from fpstune.utils.winapi.session import registry_root

        hive, full_path = registry_root(root, path)
        access = winreg.KEY_READ
        if root == "HKLM":
            access |= winreg.KEY_WOW64_64KEY
        with winreg.OpenKey(hive, full_path, 0, access):
            return True
    except FileNotFoundError:
        return False
    except OSError as exc:  # pragma: no cover - environment dependent
        logger.debug("registry probe failed for %s\\%s: %s", root, path, exc)
        return False


def _docker_desktop() -> VirtualizationConsumer | None:
    """Docker Desktop, wherever this machine put it."""
    for path, root in _DOCKER_UNINSTALL_KEYS:
        if _registry_key_exists(root, path):
            scope = "machine-wide" if root == "HKLM" else "per-user"
            return VirtualizationConsumer(
                key="docker",
                label="Docker Desktop",
                evidence=f"{scope} uninstall entry in the registry",
            )

    # Fallback for an install that left no uninstall entry — a portable copy, or
    # an engine installed without Docker Desktop. `which` reads PATH, which is
    # where any usable docker CLI has to be anyway.
    import shutil

    if shutil.which("docker"):
        return VirtualizationConsumer(
            key="docker",
            label="Docker",
            evidence="docker executable on PATH",
        )
    return None


def _wsl_distributions() -> VirtualizationConsumer | None:
    """Installed WSL distributions, counted rather than merely detected.

    The count is in the label because "WSL is installed" and "your two
    development environments live here" are different weights of the same fact.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg

        from fpstune.utils.winapi.session import registry_root

        root, key_path = registry_root("HKCU", _WSL_DISTRIBUTIONS_KEY)
        with winreg.OpenKey(root, key_path) as key:
            count = winreg.QueryInfoKey(key)[0]
    except FileNotFoundError:
        return None
    except OSError as exc:  # pragma: no cover - environment dependent
        logger.debug("WSL distribution probe failed: %s", exc)
        return None

    if count <= 0:
        return None

    plural = "distribution" if count == 1 else "distributions"
    return VirtualizationConsumer(
        key="wsl",
        label=f"WSL ({count} {plural})",
        evidence=f"{count} registered under HKCU\\{_WSL_DISTRIBUTIONS_KEY}",
    )


def _hyper_v_machines() -> VirtualizationConsumer | None:
    """Virtual machines Hyper-V has been given, if any.

    The feature being installed is not the question — a machine can carry
    Hyper-V and never have made a VM. A configured VM is a thing the user built
    and would lose access to, which is what makes it worth naming.
    """
    if sys.platform != "win32":
        return None

    program_data = os.environ.get("PROGRAMDATA")
    if not program_data:
        return None

    vm_dir = Path(program_data) / "Microsoft" / "Windows" / "Hyper-V" / "Virtual Machines"
    if not vm_dir.is_dir():
        return None

    try:
        # Hyper-V writes one .vmcx per machine. Anything else in the directory
        # is its own bookkeeping and does not mean a VM exists.
        count = sum(1 for p in vm_dir.glob("*.vmcx") if p.is_file())
    except OSError as exc:  # pragma: no cover - environment dependent
        logger.debug("Hyper-V VM probe failed: %s", exc)
        return None

    if count <= 0:
        return None

    plural = "machine" if count == 1 else "machines"
    return VirtualizationConsumer(
        key="hyper_v_vm",
        label=f"Hyper-V ({count} virtual {plural})",
        evidence=f"{count} .vmcx under {vm_dir}",
    )


# Android on Windows keeps its package the way any Store app does. Absent on a
# machine that never installed it, and absent again on Windows 11 builds after
# Microsoft retired the subsystem — which is correct either way: nothing to lose.
_WSA_PACKAGE_PREFIX = "MicrosoftCorporationII.WindowsSubsystemForAndroid"


def _windows_subsystem_for_android() -> VirtualizationConsumer | None:
    if sys.platform != "win32":
        return None

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    packages = Path(local_app_data) / "Packages"
    if not packages.is_dir():
        return None

    try:
        found = any(packages.glob(f"{_WSA_PACKAGE_PREFIX}*"))
    except OSError as exc:  # pragma: no cover - environment dependent
        logger.debug("WSA probe failed: %s", exc)
        return None

    if not found:
        return None
    return VirtualizationConsumer(
        key="wsa",
        label="Windows Subsystem for Android",
        evidence="package directory under %LOCALAPPDATA%\\Packages",
    )


_PROBES = (
    _docker_desktop,
    _wsl_distributions,
    _hyper_v_machines,
    _windows_subsystem_for_android,
)


def detect_virtualization_consumers() -> list[VirtualizationConsumer]:
    """Everything installed here that the virtualization platform carries.

    An empty list means switching the platform off costs this machine nothing
    that fpstune can see — which is the only state in which either of the two
    disable settings is a safe recommendation.

    A probe that fails is skipped rather than fatal, but a failure is never read
    as "absent" in the caller's favour: each probe already returns None only
    when it positively did not find its consumer, and logs the difference.
    """
    consumers: list[VirtualizationConsumer] = []
    for probe in _PROBES:
        try:
            found = probe()
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.debug("virtualization probe %s failed: %s", probe.__name__, exc)
            continue
        if found is not None:
            consumers.append(found)
    return consumers


# The feature every consumer contributes, so a setting can ask "is anything at
# all using this?" without naming each one. The individual keys stay available
# too: `cleanup:docker_prune` wants `docker` specifically, not "some VM thing".
VIRTUALIZATION_IN_USE = "virtualization_in_use"


def virtualization_features() -> tuple[set[str], dict[str, str]]:
    """Feature flags for :class:`HardwareContext`, and what each one stands for.

    Both come out of one pass, because they are two views of the same probe
    result and running the probes twice to build them separately would read the
    registry twice per context.

    The roll-up's label is the full list, because that is the flag the two
    disabling settings gate on: "would break Docker Desktop and WSL (1
    distribution)" is a sentence someone can act on, and "would break
    virtualization_in_use" is not.
    """
    consumers = detect_virtualization_consumers()
    if not consumers:
        return set(), {}

    flags = {c.key for c in consumers} | {VIRTUALIZATION_IN_USE}

    labels = {c.key: c.label for c in consumers}
    names = [c.label for c in consumers]
    labels[VIRTUALIZATION_IN_USE] = (
        names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    )
    return flags, labels
