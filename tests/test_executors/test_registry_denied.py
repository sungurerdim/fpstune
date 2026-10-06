r"""A registry write Windows refuses is reported as what it is.

`system:widgets` on a real machine answered "Permission denied writing
HKLM\SOFTWARE\Policies\Microsoft\Dsh\AllowNewsAndInterests - run as
administrator" while fpstune was running elevated, and other HKLM writes in the
same run landed. Telling an administrator to run as administrator sends them
nowhere; the honest report is that the system itself refused the key.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from fpstune.settings.definitions import get_all_static_settings
from fpstune.settings.executors.registry import RegistryExecutor

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Writes through winreg")

_TARGET = r"HKLM\SOFTWARE\Policies\Microsoft\Dsh\AllowNewsAndInterests"


@pytest.fixture
def widgets():
    return next(s for s in get_all_static_settings() if s.id == "system:widgets")


def _refused(*_args, **_kwargs):
    raise PermissionError(5, "Access is denied")


class TestElevated:
    def test_a_refused_write_does_not_ask_an_administrator_to_run_as_one(self, widgets) -> None:
        with (
            patch("fpstune.utils.admin.is_admin", return_value=True),
            patch("winreg.CreateKeyEx", side_effect=_refused),
        ):
            ok, error = RegistryExecutor().apply(widgets, "disabled")

        assert ok is False
        assert error is not None
        assert _TARGET in error
        assert "run as administrator" not in error
        assert "protects this key" in error

    def test_a_refused_delete_names_the_key_too(self, widgets) -> None:
        """Reset of widgets deletes the policy value."""
        with (
            patch("fpstune.utils.admin.is_admin", return_value=True),
            patch("winreg.OpenKey", side_effect=_refused),
        ):
            ok, error = RegistryExecutor().apply(widgets, "enabled")

        assert ok is False
        assert error is not None
        assert _TARGET in error
        assert "run as administrator" not in error


class TestNotElevated:
    def test_the_advice_to_run_as_administrator_stays(self, widgets) -> None:
        with (
            patch("fpstune.utils.admin.is_admin", return_value=False),
            patch("winreg.CreateKeyEx", side_effect=_refused),
        ):
            ok, error = RegistryExecutor().apply(widgets, "disabled")

        assert ok is False
        assert error == f"Permission denied writing {_TARGET} - run as administrator"
