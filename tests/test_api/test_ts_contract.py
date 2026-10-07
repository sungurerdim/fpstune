"""The frontend's response types name the fields the backend's OpenAPI schema names.

`frontend/src/lib/api.ts` types every response by hand (owner decision: no
code generator, no new dependency), and the frontend reads the backend's
snake_case keys verbatim — nothing converts case on the way in. A field renamed
on one side and not the other compiles, type-checks and ships: the UI reads
`undefined` and renders an empty cell. This file catches that drift.

How it works:

- Every `fetchJson<T>(path, ...)` and `postEventStream(path, ...)` call in
  `api.ts` is read from the source, with its method and its response type `T`.
- `_ROUTES` names, for every route `api.ts` calls, the schema component the
  route answers with — or why it has none (`_UNMODELLED`). A call missing from
  the table fails, a table entry no call uses fails, and an entry whose
  component disagrees with the OpenAPI document fails.
- `T` is resolved against the interfaces declared in `api.ts` and the type
  files it imports, and compared with the component field by field, following
  nested models (`HardwareInfo.monitors` -> `MonitorInfo`) on both sides.
  A field the frontend types that the schema does not carry is a mismatch.

Fields the schema carries and the frontend does not type are not a mismatch:
TypeScript types are structural, and a frontend that never reads a field has
no name to disagree on.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from fpstune.api.main import create_app

ROOT = Path(__file__).resolve().parents[2]
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"

# (METHOD, OpenAPI path) -> the component its 2xx response is.
_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/api/system"): "SystemInfo",
    ("GET", "/api/hardware"): "HardwareInfo",
    ("GET", "/api/activity"): "ActivityLogResponse",
    ("POST", "/api/display/{display_index}/auto"): "DisplayAutoResponse",
    ("POST", "/api/display/keep-all"): "DisplayConfirmResponse",
    ("POST", "/api/display/{display_index}/confirm"): "DisplayConfirmResponse",
    ("POST", "/api/display/refresh"): "RefreshDisplaysResponse",
    ("POST", "/api/network/refresh"): "NetworkRefreshResponse",
    ("POST", "/api/audio/refresh"): "AudioRefreshResponse",
    ("GET", "/api/settings/definitions"): "SettingDefinitionResponse",
    ("POST", "/api/settings/detect"): "DetectResponse",
    ("POST", "/api/settings/{setting_id}/apply"): "ApplyResponse",
    ("GET", "/api/settings/categories/metadata"): "CategoryMetadataResponse",
    ("GET", "/api/settings/modules/metadata"): "ModuleMetadataResponse",
    ("GET", "/api/update/check"): "UpdateStatus",
    ("POST", "/api/update/install"): "UpdateInstallResult",
}

# Routes api.ts calls whose OpenAPI response declares no fields, so there is
# nothing to hold the frontend's type against. Each is a backend route
# returning a bare dict (or a stream); `test_unmodelled_routes_really_have_no_model`
# fails the moment one gains a response model, so it moves to `_ROUTES`.
_SSE = "server-sent events; the frontend types each event as Record<string, unknown>"
_DICT = "the route returns a bare dict: no response model, no field names in the schema"
_UNMODELLED: dict[tuple[str, str], str] = {
    ("POST", "/api/settings/bulk/stream-apply"): _SSE,
    ("POST", "/api/benchmark/suite/run"): _SSE,
    ("POST", "/api/audio/device/{device_id}/loudness-eq"): _DICT,
    ("POST", "/api/audio/device/{device_id}/enabled"): _DICT,
    ("POST", "/api/network/adapter/{adapter_name}/connection/{action}"): _DICT,
    ("POST", "/api/storage/{drive_letter}/optimize"): _DICT,
    ("POST", "/api/restore-point"): _DICT,
    ("GET", "/api/self-check"): _DICT,
    ("GET", "/api/os-build"): _DICT,
    ("GET", "/api/display/pending"): _DICT,
    ("GET", "/api/settings/cleanup-sizes"): _DICT,
    ("GET", "/api/benchmark/suite"): _DICT,
    ("POST", "/api/benchmark/suite/compare"): _DICT,
    ("GET", "/api/benchmark/ledger"): _DICT,
    ("POST", "/api/benchmark/ledger/run"): _DICT,
    ("GET", "/api/benchmark/ledger/runs"): _DICT,
    ("POST", "/api/benchmark/verify/coverage"): _DICT,
    ("GET", "/api/benchmark/verify/sources"): _DICT,
    ("POST", "/api/benchmark/verify/sample"): _DICT,
    ("POST", "/api/benchmark/verify/round"): _DICT,
    ("GET", "/api/benchmark/headroom"): _DICT,
    ("POST", "/api/benchmark/headroom/measure"): _DICT,
    ("GET", "/api/benchmark/gpu-scene"): _DICT,
    ("POST", "/api/benchmark/gpu-scene/install"): _DICT,
}


# ---------------------------------------------------------------------------
# A small TypeScript reader: comments, interfaces, object literals, calls.
# ---------------------------------------------------------------------------


def _strip_comments(src: str) -> str:
    """Blank out `//` and `/* */` comments, leaving string literals intact.

    Offsets are preserved (comments become spaces, newlines kept), so a
    position found in the stripped text is the same position in the source.
    """
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch in "\"'`":
            j = i + 1
            while j < n and src[j] != ch:
                j += 2 if src[j] == "\\" else 1
            i = j + 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j == -1 else j
            out[i:j] = " " * (j - i)
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out[i:j] = [c if c == "\n" else " " for c in src[i:j]]
            i = j
        else:
            i += 1
    return "".join(out)


_OPEN = {"{": "}", "(": ")", "[": "]", "<": ">"}
_CLOSE = {v: k for k, v in _OPEN.items()}


def _match(src: str, start: int) -> int:
    """Index of the bracket closing the one at `start` (strings and `=>` skipped)."""
    stack: list[str] = []
    i = start
    while i < len(src):
        ch = src[i]
        if ch in "\"'`":
            j = i + 1
            while j < len(src) and src[j] != ch:
                j += 2 if src[j] == "\\" else 1
            i = j + 1
            continue
        if src.startswith("=>", i):
            i += 2
            continue
        if ch in _OPEN:
            stack.append(ch)
        elif ch in _CLOSE:
            if not stack or stack[-1] != _CLOSE[ch]:
                raise ValueError(f"unbalanced {ch!r} at {i}: {src[max(0, i - 60) : i + 1]!r}")
            stack.pop()
            if not stack:
                return i
        i += 1
    raise ValueError(f"no close for {src[start]!r} at {start}")


def _split_top(text: str, seps: str) -> list[str]:
    """Split on any of `seps` that sits outside every bracket and string."""
    parts: list[str] = []
    depth, last, i = 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch in "\"'`":
            j = i + 1
            while j < len(text) and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if text.startswith("=>", i):
            i += 2
            continue
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        elif depth == 0 and ch in seps:
            parts.append(text[last:i])
            last = i + 1
        i += 1
    parts.append(text[last:])
    return parts


_MEMBER = re.compile(
    r"^\s*(?:readonly\s+)?([A-Za-z_$][\w$]*|\"[^\"]+\"|'[^']+')\s*(\?)?\s*:(.*)$", re.S
)


# Members that name no field: a method signature (the logger's) or an index
# signature (`Finding`'s `[key: string]: unknown`).
_METHOD = re.compile(r"^\s*(?:\[|[A-Za-z_$][\w$]*\s*\??\s*[(<])")


@dataclass(frozen=True)
class ObjectType:
    """An object shape: field name -> its type text."""

    fields: dict[str, str]


def _parse_members(body: str) -> ObjectType:
    """Fields of an interface body or `{ ... }` literal (without the braces).

    Members end at a top-level `;` or `,`, or at a newline when the next line
    opens a new member — a union may not wrap at top level without one.
    """
    fields: dict[str, str] = {}
    chunks: list[str] = []
    for part in _split_top(body, ";,"):
        lines = _split_top(part, "\n")
        current = ""
        for line in lines:
            if current.strip() and _MEMBER.match(line):
                chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        chunks.append(current)
    for chunk in chunks:
        if not chunk.strip() or _METHOD.match(chunk):
            continue
        found = _MEMBER.match(chunk)
        if found is None:
            raise ValueError(f"unreadable member: {chunk.strip()!r}")
        fields[found.group(1).strip("\"'")] = " ".join(found.group(3).split())
    return ObjectType(fields)


_INTERFACE = re.compile(r"\binterface\s+(\w+)\s*(?:extends\s+([\w\s,]+?))?\s*\{")
_IMPORT = re.compile(r"import\s+(?:type\s+)?\{[^}]*\}\s+from\s+\"(\.[^\"]+)\"")


def _read_interfaces(src: str, into: dict[str, ObjectType]) -> None:
    extends: dict[str, list[str]] = {}
    for found in _INTERFACE.finditer(src):
        name = found.group(1)
        open_at = found.end() - 1
        into[name] = _parse_members(src[open_at + 1 : _match(src, open_at)])
        if found.group(2):
            extends[name] = [p.strip() for p in found.group(2).split(",")]
    for name, parents in extends.items():
        merged: dict[str, str] = {}
        for parent in parents:
            merged.update(into[parent].fields)
        merged.update(into[name].fields)
        into[name] = ObjectType(merged)


def _load_ts(sources: dict[Path, str]) -> dict[str, ObjectType]:
    interfaces: dict[str, ObjectType] = {}
    for src in sources.values():
        _read_interfaces(src, interfaces)
    return interfaces


def _ts_sources(api_src: str) -> dict[Path, str]:
    """api.ts plus every relative module it imports from, comments stripped."""
    sources = {API_TS: _strip_comments(api_src)}
    for rel in _IMPORT.findall(sources[API_TS]):
        path = (API_TS.parent / rel).resolve().with_suffix(".ts")
        sources[path] = _strip_comments(path.read_text(encoding="utf-8"))
    return sources


@dataclass(frozen=True)
class Call:
    """One request api.ts makes."""

    method: str
    path: str  # the TS path, interpolations kept verbatim
    response: str | None  # the `fetchJson<T>` type text; None for a stream


def _first_string(text: str) -> str:
    found = re.match(r"\s*([\"`])", text)
    if found is None:
        raise ValueError(f"call does not start with a path literal: {text[:60]!r}")
    quote = found.group(1)
    start = found.end()
    end = text.index(quote, start)
    return text[start:end]


def _read_calls(src: str) -> list[Call]:
    calls: list[Call] = []
    for found in re.finditer(r"\bfetchJson<", src):
        lt = found.end() - 1
        gt = _match(src, lt)
        if src[gt + 1] != "(":
            continue  # the declaration `async function fetchJson<T>(url...`
        close = _match(src, gt + 1)
        args = src[gt + 2 : close]
        if not re.match(r"\s*[\"`]", args):
            continue  # `fetchJson<T>(url: string, ...)` itself
        method = re.search(r"method:\s*\"(\w+)\"", args)
        calls.append(
            Call(
                method.group(1) if method else "GET",
                _first_string(args),
                " ".join(src[lt + 1 : gt].split()),
            )
        )
    for found in re.finditer(r"\bpostEventStream\(", src):
        args = src[found.end() : _match(src, found.end() - 1)]
        if re.match(r"\s*[\"`]", args):
            calls.append(Call("POST", _first_string(args), None))
    return calls


def _route_of(call: Call, operations: set[tuple[str, str]]) -> tuple[str, str]:
    """The one OpenAPI operation a call reaches."""
    path = call.path
    # Rebuild with each `${...}` (balanced) turned into a wildcard.
    pattern, i = "", 0
    while i < len(path):
        if path.startswith("${", i):
            end = _match(path, i + 1)
            pattern += "[^/]*"
            i = end + 1
        elif path[i] == "?":
            break  # a literal query string is not part of the route
        else:
            pattern += re.escape(path[i])
            i += 1
    regex = re.compile("/api" + pattern)
    hits = [op for op in operations if op[0] == call.method and regex.fullmatch(op[1])]
    if len(hits) != 1:
        raise AssertionError(
            f"{call.method} {call.path} reaches {len(hits)} operations: {sorted(hits)}"
        )
    return hits[0]


# ---------------------------------------------------------------------------
# The comparison.
# ---------------------------------------------------------------------------


def _schema_shape(
    node: dict[str, Any], components: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    """The component an OpenAPI node holds, through null unions, arrays and maps."""
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        component = components[name]
        return (name, component) if component.get("properties") else None
    for variant in node.get("anyOf", []):
        shape = _schema_shape(variant, components)
        if shape is not None:
            return shape
    if isinstance(node.get("items"), dict):
        return _schema_shape(node["items"], components)
    if isinstance(node.get("additionalProperties"), dict):
        return _schema_shape(node["additionalProperties"], components)
    return None


def _ts_shape(type_text: str, interfaces: dict[str, ObjectType]) -> tuple[str, ObjectType] | None:
    """The object shape a TS type holds, through `| null`, `[]` and `Record<string, X>`."""
    text = type_text.strip()
    if text.startswith("{"):
        end = _match(text, 0)
        return "{...}", _parse_members(text[1:end])
    record = re.fullmatch(r"Record<\s*string\s*,(.*)>", text, re.S)
    if record:
        return _ts_shape(record.group(1), interfaces)
    variants = [v for v in _split_top(text, "|") if v.strip() not in ("null", "undefined", "")]
    if len(variants) > 1:
        shapes = [s for v in variants if (s := _ts_shape(v, interfaces)) is not None]
        return shapes[0] if len(shapes) == 1 else None
    text = variants[0].strip() if variants else ""
    if text.endswith("[]"):
        return _ts_shape(text[:-2], interfaces)
    if text.startswith("(") and text.endswith(")"):
        return _ts_shape(text[1:-1], interfaces)
    if text in interfaces:
        return text, interfaces[text]
    return None


def _compare(
    ts_name: str,
    ts: ObjectType,
    component_name: str,
    component: dict[str, Any],
    components: dict[str, Any],
    interfaces: dict[str, ObjectType],
    where: str,
    out: list[str],
) -> None:
    props: dict[str, Any] = component["properties"]
    for name, type_text in ts.fields.items():
        here = f"{where}.{name}"
        if name not in props:
            out.append(
                f"{here}: the frontend's {ts_name} types `{name}`, schema {component_name} has no such field"
            )
            continue
        schema_child = _schema_shape(props[name], components)
        ts_child = _ts_shape(type_text, interfaces)
        if schema_child is not None and ts_child is not None:
            _compare(
                ts_child[0],
                ts_child[1],
                schema_child[0],
                schema_child[1],
                components,
                interfaces,
                here,
                out,
            )
        elif ts_child is not None and schema_child is None:
            out.append(
                f"{here}: the frontend types an object ({ts_child[0]}), schema declares no fields for it"
            )


def _mismatches(api_src: str, openapi: dict[str, Any]) -> list[str]:
    """Every field name the frontend types for a response that the schema lacks."""
    interfaces = _load_ts(_ts_sources(api_src))
    components: dict[str, Any] = openapi["components"]["schemas"]
    out: list[str] = []
    for call in _read_calls(_strip_comments(api_src)):
        route = _route_of(call, _operations(openapi))
        component_name = _ROUTES.get(route)
        if component_name is None or call.response is None:
            continue
        ts_shape = _ts_shape(call.response, interfaces)
        where = f"{route[0]} {route[1]}"
        if ts_shape is None:
            out.append(
                f"{where}: response type `{call.response}` is not an object shape this test can read"
            )
            continue
        _compare(
            ts_shape[0],
            ts_shape[1],
            component_name,
            components[component_name],
            components,
            interfaces,
            where,
            out,
        )
    return out


def _operations(openapi: dict[str, Any]) -> set[tuple[str, str]]:
    return {(method.upper(), path) for path, ops in openapi["paths"].items() for method in ops}


def _response_schema(openapi: dict[str, Any], route: tuple[str, str]) -> dict[str, Any]:
    responses = openapi["paths"][route[1]][route[0].lower()]["responses"]
    ok = next(code for code in responses if code.startswith("2"))
    schema: dict[str, Any] = (
        responses[ok].get("content", {}).get("application/json", {}).get("schema", {})
    )
    return schema


@cache
def _openapi() -> dict[str, Any]:
    schema: dict[str, Any] = create_app().openapi()
    return schema


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    return copy.deepcopy(_openapi())


@pytest.fixture(scope="module")
def api_src() -> str:
    return API_TS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


def test_every_route_api_ts_calls_is_in_the_table(api_src: str, openapi: dict[str, Any]) -> None:
    """A call the table does not name would go unchecked; an entry no call uses is stale."""
    called = {_route_of(c, _operations(openapi)) for c in _read_calls(_strip_comments(api_src))}
    tabled = set(_ROUTES) | set(_UNMODELLED)
    assert not set(_ROUTES) & set(_UNMODELLED), "a route is both modelled and unmodelled"
    assert sorted(called - tabled) == [], "api.ts calls these routes; name their response component"
    assert sorted(tabled - called) == [], "no api.ts call reaches these routes any more; drop them"


def test_table_components_are_what_the_routes_return(openapi: dict[str, Any]) -> None:
    """`_ROUTES` must agree with the OpenAPI document, or it checks the wrong model."""
    wrong = {}
    for route, component in _ROUTES.items():
        shape = _schema_shape(_response_schema(openapi, route), openapi["components"]["schemas"])
        if shape is None or shape[0] != component:
            wrong[route] = shape[0] if shape else None
    assert wrong == {}


def test_unmodelled_routes_really_have_no_model(openapi: dict[str, Any]) -> None:
    """The day a route gains a response model, it leaves `_UNMODELLED` for `_ROUTES`."""
    gained = [
        route
        for route in _UNMODELLED
        if _schema_shape(_response_schema(openapi, route), openapi["components"]["schemas"])
        is not None
    ]
    assert gained == []


def test_frontend_response_fields_exist_in_the_schema(
    api_src: str, openapi: dict[str, Any]
) -> None:
    """Every field api.ts (and the types it imports) names on a response is in the schema."""
    assert _mismatches(api_src, openapi) == []


def test_reader_sees_every_typed_response(api_src: str) -> None:
    """Non-vacuity: the reader found the calls and the interfaces it is meant to check."""
    calls = _read_calls(_strip_comments(api_src))
    interfaces = _load_ts(_ts_sources(api_src))
    assert len(calls) >= len(_ROUTES) + len(_UNMODELLED)
    assert sum(c.response is not None for c in calls) >= len(_ROUTES)
    for name in (
        "HardwareInfo",
        "MonitorInfo",
        "SettingState",
        "ApplyResponse",
        "SettingDefinition",
    ):
        assert interfaces[name].fields, name
    assert "refresh_rate_hz" in interfaces["MonitorInfo"].fields
    assert "default_source" in interfaces["SettingState"].fields


def test_a_renamed_schema_field_is_caught(api_src: str, openapi: dict[str, Any]) -> None:
    """Red proof, backend side: rename a nested schema field and the check names it."""
    renamed = copy.deepcopy(openapi)
    props = renamed["components"]["schemas"]["MonitorInfo"]["properties"]
    props["refresh_hz"] = props.pop("refresh_rate_hz")
    found = _mismatches(api_src, renamed)
    assert any(".monitors.refresh_rate_hz" in m and "GET /api/hardware" in m for m in found), found


def test_a_renamed_frontend_field_is_caught(api_src: str, openapi: dict[str, Any]) -> None:
    """Red proof, frontend side: rename a field in a copy of api.ts and the check names it."""
    assert "  requires_reboot: boolean;\n  skipped?" in api_src
    edited = api_src.replace(
        "  requires_reboot: boolean;\n  skipped?", "  needs_reboot: boolean;\n  skipped?"
    )
    found = _mismatches(edited, openapi)
    assert any("ApplyResponse" in m and "`needs_reboot`" in m for m in found), found


def test_an_inline_response_type_is_checked(api_src: str, openapi: dict[str, Any]) -> None:
    """`fetchJson<{ ... }>` literals are compared too, not only named interfaces."""
    edited = api_src.replace("revert_timeout_s: number | null;", "revert_timeout: number | null;")
    assert edited != api_src
    found = _mismatches(edited, openapi)
    assert any("/auto.revert_timeout" in m and "DisplayAutoResponse" in m for m in found), found
