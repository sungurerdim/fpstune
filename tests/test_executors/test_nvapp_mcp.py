"""The NVIDIA App's two frame caps are read and written through its MCP endpoint.

The point of these tests is the absence rule: the row may never say "off" for a
feature nothing could read. Every failure path here — no manifest, an App that
is not running, an unsupported feature, an answer without a boolean — must come
back as ``not_available`` so the row goes away instead of claiming a state.
"""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from fpstune.settings.applicability import NOT_AVAILABLE
from fpstune.settings.executors import nvapp_mcp


def _manifest(tmp_path: Path, url: str = "http://127.0.0.1:13508/mcp") -> Path:
    path = tmp_path / "server.json"
    path.write_text(json.dumps({"name": "nvidia-app", "http": url}), encoding="utf-8")
    return path


class _FakeServer:
    """A tool call recorded, and the answer it gives."""

    def __init__(self, payload: dict[str, Any] | None = None, error: dict[str, Any] | None = None):
        self.payload = payload
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(
        self, tool: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        self.calls.append((tool, arguments))
        if self.error is not None:
            return None, str(self.error.get("message"))
        return self.payload, None


@pytest.fixture
def features(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Drive `_call` directly so no socket is opened."""
    holder: dict[str, Any] = {}

    def install(server: Any) -> _FakeServer:
        holder["called"] = []

        def fake_call(url: str, tool: str, arguments: dict[str, Any]):
            holder["called"].append((url, tool, arguments))
            return server(tool, arguments)

        monkeypatch.setattr(nvapp_mcp, "_call", fake_call)
        return server

    holder["install"] = install
    return holder


def test_the_endpoint_is_the_url_the_app_advertises(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, "http://127.0.0.1:9999/mcp")
    assert nvapp_mcp.endpoint(manifest) == "http://127.0.0.1:9999/mcp"


def test_a_missing_manifest_advertises_nothing(tmp_path: Path) -> None:
    assert nvapp_mcp.endpoint(tmp_path / "absent.json") is None


def test_an_unreadable_manifest_advertises_nothing(tmp_path: Path) -> None:
    broken = tmp_path / "server.json"
    broken.write_text("{not json", encoding="utf-8")
    assert nvapp_mcp.endpoint(broken) is None


def test_an_enabled_feature_reads_enabled(features: dict[str, Any]) -> None:
    features["install"](
        _FakeServer({"batteryBoost": {"supported": True, "enabled": True, "frameRate": 30}})
    )
    assert nvapp_mcp.feature_state("battery_boost", "http://127.0.0.1:1/mcp") == "enabled"


def test_a_disabled_feature_reads_disabled(features: dict[str, Any]) -> None:
    features["install"](
        _FakeServer({"whisperMode": {"supported": True, "enabled": False, "fanVolume": "Balanced"}})
    )
    assert nvapp_mcp.feature_state("whisper_mode", "http://127.0.0.1:1/mcp") == "disabled"


def test_an_unsupported_feature_is_not_available_not_off(features: dict[str, Any]) -> None:
    """The machine it cannot run on must not read as a machine with the cap off."""
    features["install"](_FakeServer({"batteryBoost": {"supported": False}}))
    assert nvapp_mcp.feature_state("battery_boost", "http://127.0.0.1:1/mcp") == NOT_AVAILABLE


def test_an_answer_without_a_boolean_is_not_a_state(features: dict[str, Any]) -> None:
    features["install"](_FakeServer({"batteryBoost": {"supported": True, "enabled": "maybe"}}))
    assert nvapp_mcp.feature_state("battery_boost", "http://127.0.0.1:1/mcp") == NOT_AVAILABLE


def test_a_closed_app_is_not_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint exists but nobody answers: an absence, never a state."""

    def unreachable(*_args: Any, **_kwargs: Any) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(nvapp_mcp, "_post", unreachable)
    assert nvapp_mcp.feature_state("battery_boost", "http://127.0.0.1:1/mcp") == NOT_AVAILABLE


def test_no_endpoint_means_no_call(features: dict[str, Any]) -> None:
    server = features["install"](_FakeServer({}))
    assert nvapp_mcp.feature_state("battery_boost", None) == NOT_AVAILABLE
    assert server.calls == []


def test_an_unknown_feature_is_never_guessed(features: dict[str, Any]) -> None:
    server = features["install"](_FakeServer({}))
    assert nvapp_mcp.feature_state("turbo_button", "http://127.0.0.1:1/mcp") == NOT_AVAILABLE
    assert server.calls == []


def test_writing_off_sends_the_feature_and_then_reads_it_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A write is verified: the App's acknowledgement is not the state (C6)."""
    answers = iter(
        [
            ({}, None),
            ({"batteryBoost": {"supported": True, "enabled": False}}, None),
        ]
    )
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_call(url: str, tool: str, arguments: dict[str, Any]):
        del url
        calls.append((tool, arguments))
        return next(answers)

    monkeypatch.setattr(nvapp_mcp, "_call", fake_call)
    ok, error = nvapp_mcp.set_feature_state("battery_boost", False, "http://127.0.0.1:1/mcp")

    assert (ok, error) == (True, None)
    assert calls[0] == ("nvapp_client_set_laptop_feature", {"batteryBoost": {"enabled": False}})
    assert calls[1][0] == "nvapp_client_get_laptop_features"


def test_a_write_the_app_does_not_report_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(
        [
            ({}, None),
            ({"whisperMode": {"supported": True, "enabled": True}}, None),
        ]
    )
    monkeypatch.setattr(nvapp_mcp, "_call", lambda _url, _tool, _arguments: next(answers))
    ok, error = nvapp_mcp.set_feature_state("whisper_mode", False, "http://127.0.0.1:1/mcp")

    assert ok is False
    assert error is not None and "acknowledged" in error


def test_without_an_endpoint_nothing_is_written(features: dict[str, Any]) -> None:
    server = features["install"](_FakeServer({}))
    ok, error = nvapp_mcp.set_feature_state("battery_boost", False, "")
    assert ok is False
    assert error is not None and "MCP server was not found" in error
    assert server.calls == []


def test_the_definition_writes_only_a_display_value(features: dict[str, Any]) -> None:
    """A detector's reading ("not_available") must never be written into the App."""
    server = features["install"](_FakeServer({}))
    ok, error = nvapp_mcp.nvapp_laptop_feature_write(
        {"feature": "battery_boost", "value": NOT_AVAILABLE, "allowed": "enabled,disabled"}
    )
    assert ok is False
    assert error is not None and "reading" in error
    assert server.calls == []


def test_the_detector_entry_answers_the_rows_own_feature(
    features: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    features["install"](_FakeServer({"batteryBoost": {"supported": True, "enabled": False}}))
    monkeypatch.setattr(nvapp_mcp, "endpoint", lambda _manifest=None: "http://127.0.0.1:1/mcp")
    assert nvapp_mcp.nvapp_laptop_feature_read({"feature": "battery_boost"}) == "disabled"
