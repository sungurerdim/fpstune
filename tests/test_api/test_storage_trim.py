"""TRIM state comes from the registry value the setting writes, never from fsutil text.

The defect: ``fsutil behavior query DisableDeleteNotify`` was piped through
``Select-String 'NTFS'`` and the check was ``"0" in output``. fsutil answers in
the system language, so a localized label could be read as a value, and a
failed read came back as "TRIM off". The registry is locale-free, and a key that
cannot be opened is now *unknown* — the card says it could not tell rather than
showing a warning nothing measured.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import fpstune.api.hardware.storage as storage

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="winreg is Windows only")


class _FakeKey:
    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def __enter__(self) -> _FakeKey:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def query(self, name: str) -> tuple[object, int]:
        if name not in self._values:
            raise FileNotFoundError(name)
        return self._values[name], 4


def _with_registry(monkeypatch: pytest.MonkeyPatch, values: dict[str, object] | None) -> None:
    import winreg

    if values is None:

        def open_key(*_a: object, **_k: object) -> _FakeKey:
            raise PermissionError("access denied")

    else:
        key = _FakeKey(values)

        def open_key(*_a: object, **_k: object) -> _FakeKey:
            return key

    monkeypatch.setattr(winreg, "OpenKey", open_key)
    monkeypatch.setattr(winreg, "QueryValueEx", lambda k, name: k.query(name))


class TestTheRegistryIsTheSource:
    def test_an_absent_value_is_windows_stock_trim_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _with_registry(monkeypatch, {})
        assert storage._trim_is_enabled() is True

    def test_zero_is_on_and_one_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _with_registry(monkeypatch, {"DisableDeleteNotify": 0})
        assert storage._trim_is_enabled() is True
        _with_registry(monkeypatch, {"DisableDeleteNotify": 1})
        assert storage._trim_is_enabled() is False

    def test_an_unreadable_key_is_unknown_never_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A11: 'could not read' must not look like a state."""
        _with_registry(monkeypatch, None)
        assert storage._trim_is_enabled() is None

    def test_a_value_of_the_wrong_type_is_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _with_registry(monkeypatch, {"DisableDeleteNotify": "garbage"})
        assert storage._trim_is_enabled() is None

    def test_the_module_no_longer_reads_fsutil_text(self) -> None:
        source = Path(storage.__file__).read_text(encoding="utf-8")
        assert "fsutil behavior query" not in source
        assert "Select-String" not in source


class TestOnlyAnSsdCarriesTheAnswer:
    def test_an_hdd_is_not_applicable_rather_than_off(self) -> None:
        payload = json.dumps(
            [
                {
                    "DriveLetter": "C",
                    "Model": "Samsung 990",
                    "SizeGB": 931,
                    "FreeGB": 400,
                    "MediaType": "SSD",
                    "BusType": "NVMe",
                    "UniqueId": "eui.1",
                },
                {
                    "DriveLetter": "D",
                    "Model": "WD Blue",
                    "SizeGB": 1863,
                    "FreeGB": 900,
                    "MediaType": "HDD",
                    "BusType": "SATA",
                    "UniqueId": "WD-1",
                },
            ]
        )
        with (
            patch.object(storage, "run_powershell", return_value=(True, payload)),
            patch.object(storage, "_trim_is_enabled", return_value=True),
        ):
            drives = storage.get_detailed_storage_drives()
        by_letter = {d.drive_letter: d for d in drives}
        assert by_letter["C"].trim_enabled is True
        assert by_letter["D"].trim_enabled is None

    def test_an_unknown_state_reaches_the_ssd_as_unknown(self) -> None:
        payload = json.dumps(
            [
                {
                    "DriveLetter": "C",
                    "Model": "Samsung 990",
                    "SizeGB": 931,
                    "FreeGB": 400,
                    "MediaType": "SSD",
                    "BusType": "NVMe",
                    "UniqueId": "eui.1",
                }
            ]
        )
        with (
            patch.object(storage, "run_powershell", return_value=(True, payload)),
            patch.object(storage, "_trim_is_enabled", return_value=None),
        ):
            drives = storage.get_detailed_storage_drives()
        assert drives[0].trim_enabled is None
