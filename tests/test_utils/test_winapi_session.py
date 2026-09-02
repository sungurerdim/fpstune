"""HKCU means the person at the keyboard, not whoever's token the process carries.

A standard user who elevates with an administrator's password runs fpstune as
that administrator; ``HKEY_CURRENT_USER`` is then the administrator's hive and
every per-user tweak lands in the wrong account. The decision — write under
``HKEY_USERS\\<SID>`` only when the console user differs from the process user
and that hive is loaded — is a pure function here, and the two SID readers are
proven on the running machine.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.utils.winapi import session
from fpstune.utils.winapi.session import UserHive, resolve_user_hive

ADMIN = "S-1-5-21-1000-2000-3000-500"
PLAYER = "S-1-5-21-1000-2000-3000-1001"


class TestTheDecision:
    def test_same_user_keeps_hkcu(self) -> None:
        """The common case: the player elevated their own account."""
        assert resolve_user_hive(PLAYER, PLAYER, True) == UserHive("HKCU", "")

    def test_a_different_console_user_with_a_loaded_hive_is_written_under_hku(self) -> None:
        """The defect: the token is the administrator's, the keyboard is the player's."""
        hive = resolve_user_hive(ADMIN, PLAYER, True)
        assert hive == UserHive("HKU", f"{PLAYER}\\")
        assert hive.path(r"Software\Microsoft\GameBar") == rf"{PLAYER}\Software\Microsoft\GameBar"

    def test_an_unloaded_hive_falls_back_to_hkcu(self) -> None:
        """Writing under a SID whose hive is not mounted would create an orphan key."""
        assert resolve_user_hive(ADMIN, PLAYER, False) == UserHive("HKCU", "")

    def test_no_console_user_falls_back_to_hkcu(self) -> None:
        """A service session or a headless run has nobody at the keyboard."""
        assert resolve_user_hive(ADMIN, None, False) == UserHive("HKCU", "")
        assert resolve_user_hive(None, PLAYER, True) == UserHive("HKCU", "")


@pytest.mark.skipif(sys.platform != "win32", reason="reads the running session")
class TestTheRealMachine:
    def test_the_process_sid_is_a_domain_or_local_account(self) -> None:
        sid = session.process_user_sid()
        assert sid is not None
        assert sid.startswith("S-1-5-")

    def test_the_console_user_resolves_or_is_honestly_absent(self) -> None:
        sid = session.interactive_user_sid()
        assert sid is None or sid.startswith("S-1-5-")

    def test_the_resolved_hive_is_consistent_with_the_two_sids(self) -> None:
        session.user_hive.cache_clear()
        hive = session.user_hive()
        if session.interactive_user_sid() == session.process_user_sid():
            assert hive == UserHive("HKCU", "")
        else:
            assert hive.root in ("HKCU", "HKU")


class TestRedirectingPowerShell:
    """`HKCU:` in a shipped script is rewritten to the console user's hive, or left alone."""

    STEAM = "$val = (Get-ItemProperty -Path 'HKCU:\\Software\\Valve\\Steam' -Name 'x').x"

    def test_another_console_user_gets_a_provider_qualified_path(self, monkeypatch) -> None:
        monkeypatch.setattr(session, "user_hive", lambda: UserHive("HKU", f"{PLAYER}\\"))
        out = session.redirect_hkcu(self.STEAM)
        assert out == (
            f"$val = (Get-ItemProperty -Path 'Registry::HKEY_USERS\\{PLAYER}\\Software\\Valve\\Steam'"
            " -Name 'x').x"
        )

    def test_the_players_own_session_leaves_the_script_untouched(self, monkeypatch) -> None:
        monkeypatch.setattr(session, "user_hive", lambda: UserHive("HKCU", ""))
        assert session.redirect_hkcu(self.STEAM) == self.STEAM

    def test_every_spelling_of_the_drive_is_rewritten_and_hklm_is_not(self, monkeypatch) -> None:
        monkeypatch.setattr(session, "user_hive", lambda: UserHive("HKU", f"{PLAYER}\\"))
        script = "Test-Path 'hkcu:\\A'; Test-Path 'HKLM:\\B'; $p = 'HKCU:\\C'"
        out = session.redirect_hkcu(script)
        assert "HKCU:" not in out.upper().replace("REGISTRY::HKEY_USERS", "")
        assert "HKLM:\\B" in out
        assert out.count(f"Registry::HKEY_USERS\\{PLAYER}\\") == 2

    def test_a_script_without_the_drive_never_resolves_the_session(self, monkeypatch) -> None:
        """Most scripts touch no per-user key; they must not pay for the lookup."""

        def explode() -> UserHive:
            raise AssertionError("user_hive() resolved for a script without HKCU:")

        monkeypatch.setattr(session, "user_hive", explode)
        assert session.redirect_hkcu("Get-NetAdapter") == "Get-NetAdapter"


class TestTheWinregResolver:
    def test_hkcu_of_another_console_user_is_hkey_users_plus_sid(self, monkeypatch) -> None:
        import winreg

        monkeypatch.setattr(session, "user_hive", lambda: UserHive("HKU", f"{PLAYER}\\"))
        assert session.registry_root("HKCU", r"Software\X") == (
            winreg.HKEY_USERS,
            rf"{PLAYER}\Software\X",
        )

    def test_hklm_never_moves(self, monkeypatch) -> None:
        import winreg

        monkeypatch.setattr(session, "user_hive", lambda: UserHive("HKU", f"{PLAYER}\\"))
        assert session.registry_root("HKLM", r"SYSTEM\X") == (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\X",
        )


@pytest.mark.skipif(sys.platform != "win32", reason="asks the Registry provider on this machine")
class TestTheProviderAcceptsWhatWeEmit:
    def test_registry_hkey_users_sid_is_a_path_powershell_resolves(self) -> None:
        """Read-only: the exact path shape `redirect_hkcu` produces, for this process's
        own SID, must be one `Test-Path` answers True to — otherwise every redirected
        script would fail at binding rather than at the wrong hive."""
        import subprocess

        sid = session.process_user_sid()
        assert sid is not None
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Test-Path 'Registry::HKEY_USERS\\{sid}\\Software'",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.stdout.strip() == "True", result.stderr
