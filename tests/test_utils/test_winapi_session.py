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
