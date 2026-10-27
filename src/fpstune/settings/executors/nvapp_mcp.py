"""Read and set the NVIDIA App's own frame caps through its local MCP endpoint.

Battery Boost and Whisper Mode are the App's two frame caps, and until now
nothing shipped could see either one. The App does not persist their on/off
state in any file under ``NvBackend`` (searched 2026-08-23 for the battery
criteria, and again 2026-10-22 for a state store: the only files there answer
*supportability*), so reading the criteria file and reporting it as the state
was the failure the sentinel contract exists to prevent.

What the App does publish is the state itself, over the MCP server it runs
next to its UI: ``McpServer/server.json`` names the endpoint, and
``nvapp_client_get_laptop_features`` answers ``supported`` plus the effective
``enabled`` flag and the cap in force. ``nvapp_client_set_laptop_feature``
writes the same two flags. Both were exercised against this machine on
2026-10-22: a read returned ``batteryBoost {supported: true, enabled: false,
frameRate: 30}``, and a write of ``enabled: false`` was acknowledged and read
back unchanged.

The endpoint is discovered, never assumed (C9): its URL is the ``http`` field
of that manifest, so a future App that moves its port keeps working. When the
App is not running, its MCP server is not either, and every answer here is
``not_available`` — a row that cannot be read is not applicable, never "off".
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fpstune.settings.applicability import NOT_AVAILABLE
from fpstune.utils import user_paths
from fpstune.utils.logger import get_logger

logger = get_logger()

#: The App's MCP server manifest, relative to the console user's local AppData.
_MANIFEST = Path("NVIDIA Corporation") / "NVIDIA App" / "McpServer" / "server.json"

#: The tool that answers both feature states, and the one that writes one.
_READ_TOOL = "nvapp_client_get_laptop_features"
_WRITE_TOOL = "nvapp_client_set_laptop_feature"

#: Feature name in the tool schema -> the argument key that carries it.
FEATURES: dict[str, str] = {
    "battery_boost": "batteryBoost",
    "whisper_mode": "whisperMode",
}

#: What a definition calls the global scope. The tool spells its default this way.
_GLOBAL = "global"

#: Loopback round trips, not network calls: a wedged App must not hold a scan.
_TIMEOUT_SECONDS = 5.0


def manifest_path() -> Path | None:
    """The App's MCP manifest, or None where the user has no local AppData."""
    local = user_paths.local_appdata()
    return local / _MANIFEST if local is not None else None


def endpoint(manifest: Path | None = None) -> str | None:
    """The Streamable HTTP URL the App advertises, or None when it advertises none."""
    path = manifest if manifest is not None else manifest_path()
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        logger.debug("NVIDIA App MCP manifest unreadable at %s: %s", path, exc)
        return None
    url = data.get("http") if isinstance(data, dict) else None
    return url if isinstance(url, str) and url.strip() else None


def _post(url: str, payload: dict[str, Any], session: str | None) -> tuple[Any, str | None]:
    """One JSON-RPC POST. Returns (parsed body or None, session id the server named)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session:
        headers["Mcp-Session-Id"] = session
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        named = response.headers.get("Mcp-Session-Id")
        raw = response.read().decode("utf-8", "replace")
    if not raw.strip():
        return None, named
    text = raw.lstrip()
    if text.startswith(("event:", "data:")):
        # Server-sent framing: the answer is the last data line.
        lines = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
        if not lines:
            return None, named
        raw = lines[-1]
    return json.loads(raw), named


class _Session:
    """One initialize handshake, reused for the calls a single reading needs."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.session: str | None = None
        self._next_id = 0

    def handshake(self) -> None:
        _, named = _post(
            self.url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "fpstune", "version": "1"},
                },
            },
            None,
        )
        self.session = named
        _post(self.url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, self.session)

    def call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        body, _ = _post(
            self.url,
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            },
            self.session,
        )
        return body if isinstance(body, dict) else {}


def _result_of(body: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """The structured payload of a tool result, or the error the server gave."""
    error = body.get("error")
    if isinstance(error, dict):
        return None, str(error.get("message") or "the NVIDIA App refused the request")
    result = body.get("result")
    if not isinstance(result, dict):
        return None, "the NVIDIA App answered with no result"
    if result.get("isError"):
        message = ""
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                message = str(item.get("text") or "")
                break
        return None, message or "the NVIDIA App reported an error"
    structured = result.get("structuredContent")
    return (structured if isinstance(structured, dict) else None), None


def _feature_payload(feature: str) -> str | None:
    key = FEATURES.get(feature)
    if key is None:
        logger.debug("unknown NVIDIA App feature %r", feature)
    return key


def _call(
    url: str, tool: str, arguments: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    """Run one tool call in a fresh session; (structured payload, error)."""
    if sys.platform != "win32":
        return None, NOT_AVAILABLE
    session = _Session(url)
    try:
        session.handshake()
        return _result_of(session.call(tool, arguments))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # The App is closed or its MCP server is off: nothing is known, which is
        # an absence and never a state.
        logger.debug("NVIDIA App MCP endpoint %s unavailable: %s", url, exc)
        return None, NOT_AVAILABLE


def feature_state(feature: str, url: str | None = None) -> str:
    """``enabled`` / ``disabled`` for one App feature, or ``not_available``.

    ``not_available`` covers three different absences on purpose, because all
    three mean the same thing to a row: the App is not there, the endpoint is
    not advertised, or the App reports the feature as unsupported on this
    machine. None of them may be read as "off".
    """
    payload_key = _feature_payload(feature)
    if payload_key is None:
        return NOT_AVAILABLE
    target = (url if url is not None else endpoint()) or ""
    if not target.strip():
        return NOT_AVAILABLE
    payload, error = _call(target, _READ_TOOL, {"game": _GLOBAL})
    if payload is None:
        return NOT_AVAILABLE
    feature_payload = payload.get(payload_key)
    if not isinstance(feature_payload, dict):
        return NOT_AVAILABLE
    if feature_payload.get("supported") is False:
        return NOT_AVAILABLE
    enabled = feature_payload.get("enabled")
    if not isinstance(enabled, bool):
        return NOT_AVAILABLE
    return "enabled" if enabled else "disabled"


def set_feature_state(
    feature: str, enabled: bool, url: str | None = None
) -> tuple[bool, str | None]:
    """Turn one App feature on or off, and say whether the App now reports it so."""
    payload_key = _feature_payload(feature)
    if payload_key is None:
        return False, f"fpstune has no NVIDIA App feature called '{feature}'"
    target = (url if url is not None else endpoint()) or ""
    if not target.strip():
        return False, (
            "The NVIDIA App's local MCP server was not found, so nothing was changed; "
            "start the NVIDIA App and try again"
        )
    _, error = _call(target, _WRITE_TOOL, {payload_key: {"enabled": enabled}})
    if error is not None:
        detail = "" if error == NOT_AVAILABLE else f": {error}"
        return False, (
            f"The NVIDIA App did not accept the change{detail}. Turn it off under "
            "Graphics in the NVIDIA App instead"
        )
    # The App's acknowledgement is not the state: read it back, so a silent
    # revert is reported as a failure rather than assumed away (C6).
    if feature_state(feature, target) == ("enabled" if enabled else "disabled"):
        return True, None
    return False, (
        "The NVIDIA App acknowledged the change but does not report it; "
        "check the setting under Graphics in the NVIDIA App"
    )


def nvapp_laptop_feature_read(args: dict[str, Any]) -> str:
    """``PYTHON_DETECTORS`` entry: one App frame cap's state."""
    return feature_state(str(args.get("feature", "")))


def nvapp_laptop_feature_write(args: dict[str, Any]) -> tuple[bool, str | None]:
    """``PYTHON_ACTIONS`` entry: set one App frame cap from its display value."""
    value = str(args.get("value", ""))
    allowed = str(args.get("allowed", "enabled,disabled")).split(",")
    if value not in allowed:
        return False, f"'{value}' is a reading, not a value fpstune can write"
    feature = str(args.get("feature", ""))
    enabled = value == "enabled"
    ok, error = set_feature_state(feature, enabled)
    if not ok:
        return False, error
    label = "Battery Boost" if feature == "battery_boost" else "Whisper Mode"
    return True, f"{label} is now {'on' if enabled else 'off'} in the NVIDIA App"
