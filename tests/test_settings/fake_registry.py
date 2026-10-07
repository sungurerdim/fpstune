"""A dict standing in for the registry, behind the shipped RegistryExecutor.

``RegistryExecutor`` reads and writes through ``winreg``; this swaps the five calls it
makes for a dict, so a lifecycle test (detect, apply the recommendation, detect, apply the
default, detect) runs the real executor, the real ``value_map`` / ``apply_value_map`` and
the real "absent means delete" rule without touching the machine. Machine-wide (HKLM)
keys only: a per-user key resolves its hive through the console session, which is the
thing a test must not depend on.
"""

from __future__ import annotations

from typing import Any

import pytest


class FakeRegistry:
    """``values[(path, name)]`` is the DWORD or string a key holds; a missing entry is absent."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import winreg

        self.values: dict[tuple[str, str], Any] = {}

        class _Key:
            def __init__(self, path: str) -> None:
                self.path = path.lower()

            def __enter__(self) -> _Key:
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

        def open_key(_root: int, path: str, *_args: Any) -> _Key:
            if not any(p == path.lower() for p, _ in self._lowered()):
                raise FileNotFoundError(path)
            return _Key(path)

        def create_key(_root: int, path: str, *_args: Any) -> _Key:
            return _Key(path)

        def query(key: _Key, name: str) -> tuple[Any, int]:
            for (path, value_name), value in self._lowered().items():
                if path == key.path and value_name == name:
                    return value, winreg.REG_DWORD
            raise FileNotFoundError(name)

        def set_value(key: _Key, name: str, _reserved: int, _kind: int, value: Any) -> None:
            self.values[(key.path, name)] = value

        def delete_value(key: _Key, name: str) -> None:
            if (key.path, name) not in self.values:
                raise FileNotFoundError(name)
            del self.values[(key.path, name)]

        monkeypatch.setattr(winreg, "OpenKey", open_key)
        monkeypatch.setattr(winreg, "CreateKeyEx", create_key)
        monkeypatch.setattr(winreg, "QueryValueEx", query)
        monkeypatch.setattr(winreg, "SetValueEx", set_value)
        monkeypatch.setattr(winreg, "DeleteValue", delete_value)

    def _lowered(self) -> dict[tuple[str, str], Any]:
        return {(path.lower(), name): value for (path, name), value in self.values.items()}

    def put(self, path: str, name: str, value: Any) -> None:
        self.values[(path.lower(), name)] = value

    def get(self, path: str, name: str) -> Any:
        return self.values.get((path.lower(), name))
