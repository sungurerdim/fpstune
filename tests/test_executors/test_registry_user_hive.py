"""Per-user registry settings reach the person at the keyboard, not the token's owner.

fpstune runs elevated. When a standard user elevates with an administrator's
password the token is the administrator's, and ``HKEY_CURRENT_USER`` is the
administrator's hive: Game DVR, mouse acceleration, GPU preferences — every
per-user tweak — would land in an account the player never uses. The executor
asks ``winapi.session`` whose hive HKCU should mean and, when the console user is
someone else with a loaded hive, opens ``HKEY_USERS\\<SID>\\...``. HKLM is
untouched by any of this.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Any

import pytest

from fpstune.settings.executors.registry import RegistryExecutor
from fpstune.settings.registry import SettingsRegistry
from fpstune.utils.winapi import session
from fpstune.utils.winapi.session import UserHive

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="winreg is Windows only")

PLAYER = "S-1-5-21-1000-2000-3000-1001"


@pytest.fixture(scope="module")
def hkcu_setting():
    """The first shipped registry setting that lives under HKCU."""
    reg = SettingsRegistry(discover_dynamic=False)
    for setting in reg.get_all():
        if setting.detect_type.name == "REGISTRY" and setting.detect_args.get("hive") == "HKCU":
            return setting
    pytest.fail("no HKCU registry setting is shipped")


@pytest.fixture(scope="module")
def hklm_setting():
    reg = SettingsRegistry(discover_dynamic=False)
    for setting in reg.get_all():
        if (
            setting.detect_type.name == "REGISTRY"
            and setting.detect_args.get("hive", "HKLM") == "HKLM"
        ):
            return setting
    pytest.fail("no HKLM registry setting is shipped")


class _FakeKey:
    def __enter__(self) -> _FakeKey:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


@contextmanager
def _fake_winreg(monkeypatch: pytest.MonkeyPatch, hive: UserHive):
    """Record every root/path the executor opens, and answer a DWORD 1 on read.

    Only the session's answer is faked; the resolver the executor ships runs for
    real, so a test here fails if it stops asking the session at all.
    """
    import winreg

    opened: list[tuple[int, str]] = []

    def open_key(root: int, path: str, *_a: Any, **_k: Any) -> _FakeKey:
        opened.append((root, path))
        return _FakeKey()

    monkeypatch.setattr(session, "user_hive", lambda: hive)
    monkeypatch.setattr(winreg, "OpenKey", open_key)
    monkeypatch.setattr(winreg, "CreateKeyEx", open_key)
    monkeypatch.setattr(winreg, "QueryValueEx", lambda _k, _n: (1, winreg.REG_DWORD))
    monkeypatch.setattr(winreg, "SetValueEx", lambda *_a, **_k: None)
    yield opened


class TestWhereHkcuGoes:
    def test_the_players_own_session_stays_on_hkcu(self, hkcu_setting, monkeypatch) -> None:
        import winreg

        with _fake_winreg(monkeypatch, UserHive("HKCU", "")) as opened:
            RegistryExecutor().detect(hkcu_setting)
        assert opened == [(winreg.HKEY_CURRENT_USER, hkcu_setting.detect_args["path"])]

    def test_another_console_user_is_written_under_their_sid(
        self, hkcu_setting, monkeypatch
    ) -> None:
        """The gate: the administrator's token, the player's keyboard."""
        import winreg

        with _fake_winreg(monkeypatch, UserHive("HKU", f"{PLAYER}\\")) as opened:
            RegistryExecutor().detect(hkcu_setting)
            RegistryExecutor().apply(hkcu_setting, hkcu_setting.recommended_value)
        expected_path = f"{PLAYER}\\{hkcu_setting.detect_args['path']}"
        assert opened[0] == (winreg.HKEY_USERS, expected_path)
        assert all(root == winreg.HKEY_USERS for root, _ in opened)

    def test_hklm_is_never_redirected(self, hklm_setting, monkeypatch) -> None:
        import winreg

        with _fake_winreg(monkeypatch, UserHive("HKU", f"{PLAYER}\\")) as opened:
            RegistryExecutor().detect(hklm_setting)
        assert opened == [(winreg.HKEY_LOCAL_MACHINE, hklm_setting.detect_args["path"])]


class TestTheRealResolver:
    def test_the_shipped_resolver_agrees_with_the_session_module(self) -> None:
        """Not a fake: the resolver on this machine, against the decision the
        session module publishes."""
        import winreg

        hive = session.user_hive()
        root, path = session.registry_root("HKCU", r"Software\Microsoft\GameBar")
        if hive.root == "HKCU":
            assert (root, path) == (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar")
        else:
            assert root == winreg.HKEY_USERS and path.startswith("S-1-5-")
        assert session.registry_root("HKLM", r"SYSTEM\X") == (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\X",
        )
