"""Catalogue section B and the code-shape principles, checked by reading the AST.

`tests/test_principles_architecture.py` owns the module graph; this file owns the
inside of a function. Every check is a pure AST read — no imports of the app, no
subprocess — so the whole file runs in milliseconds and can sit in the default
suite.

What it binds:

- **P-DEMETER** — no new chain of four or more attributes. The legitimate chains
  (ctypes binding setup, a before/after comparison record, a `Path`'s own
  `parent` walk) are allowlisted with their reason, and an allowance that stops
  matching is red so the list can only shrink.
- **P-ILLEGAL** — the fields that hold a small fixed vocabulary are typed
  `Literal` or a `StrEnum`, not `str`. The pinned list is the record of which
  ones were decided; it fails if a field is loosened back to `str`.
- **P-PARSE / P-POLA** — a route handler declares a typed body and never parses
  raw request JSON itself; the parse happens once at the boundary.
- **P-CQS / P-POLA** — a function whose name says it reads does not write files
  or the registry. The allowlist is empty today and can only shrink.
- **P-EXPLICIT** — every broad `except Exception`/`BaseException` that does not
  re-raise carries `# noqa: BLE001 - <reason>`, and a `try/except/pass` carries
  the same. This is the in-tree binding for the rule ruff will enforce once
  `BLE`/`S110` join `[tool.ruff.lint] select`.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "fpstune"


@functools.cache
def _source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


@functools.cache
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


@functools.cache
def _source(path: Path) -> tuple[str, ...]:
    return tuple(path.read_text(encoding="utf-8").splitlines())


# === P-DEMETER ==============================================================


def _chain_parts(node: ast.Attribute) -> list[str] | None:
    """The dotted names of a maximal attribute chain, or None if it is not one.

    Only `name.attr.attr...` counts: `f().x.y` and `items[0].x.y` are calls and
    subscripts, not a walk through somebody else's object graph.
    """
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return list(reversed(parts))


#: (path glob, chain regex) -> reason. `*` matches every file.
_ALLOWED_CHAINS: dict[tuple[str, str], str] = {
    (
        "*",
        r"self\._(?:kernel32|powrprof)\.[A-Za-z_]+\.(?:argtypes|restype)",
    ): "ctypes binding setup: argtypes/restype belong to the function, not to application data",
    (
        "src/fpstune/benchmark/dpc.py",
        r"self\.(?:before|after)\.stats\.[a-z_0-9]+",
    ): "a comparison record holds before/after stats side by side; the chain is its shape",
    (
        "src/fpstune/benchmark/network.py",
        r"self\.(?:before|after)\.stats\.[a-z_0-9]+",
    ): "a comparison record holds before/after stats side by side; the chain is its shape",
    (
        "src/fpstune/benchmark/presentmon.py",
        r"self\.(?:before|after)\.stats\.[a-z_0-9]+",
    ): "a comparison record holds before/after stats side by side; the chain is its shape",
    (
        "src/fpstune/settings/applicability.py",
        r"self\.context\.(?:cpu_vendor|gpu_vendor|feature_labels)\.(?:lower|get)",
    ): "reading a field of the context the checker was built around",
    (
        "src/fpstune/utils/instance_reclaim.py",
        r"path\.parent\.name\.casefold",
    ): "PureWindowsPath parsing: name operations on a path, not an object graph",
    (
        "src/fpstune/utils/operation_log.py",
        r"self\.path\.parent\.(?:mkdir|glob)",
    ): "Path operations on the log's own path",
}


@functools.cache
def _deep_chains() -> tuple[tuple[str, int, str], ...]:
    found: list[tuple[str, int, str]] = []
    for path in _source_files():
        tree = _tree(path)
        parents = {
            id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if isinstance(parents.get(id(node)), ast.Attribute):
                continue  # only the maximal chain, not every prefix of it
            parts = _chain_parts(node)
            if parts is None or len(parts) < 4 or parts[0] == "ctypes":
                continue
            found.append((_relative(path), node.lineno, ".".join(parts)))
    return tuple(found)


class TestDemeter:
    """P-DEMETER: talk to the object in front of you, not through it.

    A four-name chain is the first length at which the caller is reaching
    through one object to another's internals — `order.customer.address.city`.
    The ctypes idiom (`ctypes.windll.kernel32.X`) is a namespace walk rather
    than an object graph, so it is exempt by root name.
    """

    def test_no_new_chain_of_four_or_more_attributes(self) -> None:
        offenders = []
        for relative, line, text in _deep_chains():
            if any(
                (path == "*" or path == relative) and re.fullmatch(pattern, text)
                for path, pattern in _ALLOWED_CHAINS
            ):
                continue
            offenders.append(f"{relative}:{line}: {text}")
        assert not offenders, (
            "attribute chains four names deep — ask the owner for the value, or add "
            "an allowance with the reason: " + "; ".join(offenders)
        )

    def test_every_allowance_still_matches_a_chain(self) -> None:
        chains = _deep_chains()
        stale = [
            f"{path or '*'}: {pattern}"
            for path, pattern in _ALLOWED_CHAINS
            if not any(
                (path == "*" or path == relative) and re.fullmatch(pattern, text)
                for relative, _line, text in chains
            )
        ]
        assert not stale, (
            "an attribute-chain allowance no longer matches anything — delete it so "
            "the allowlist can only shrink: " + "; ".join(stale)
        )


# === P-ILLEGAL ==============================================================


@functools.cache
def _finite_type_names() -> frozenset[str]:
    """Every name in the tree that denotes a finite set of values.

    Two spellings: a class deriving from `Enum`/`StrEnum`, and a module-level
    `Name = Literal[...]` alias (`EvidenceLevel`, `RestoreKind`, ...).
    """
    names: set[str] = set()
    for path in _source_files():
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(base, ast.Name) and base.id in {"Enum", "StrEnum", "IntEnum"}
                for base in node.bases
            ):
                names.add(node.name)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                target = node.targets[0] if isinstance(node, ast.Assign) else node.target
                if (
                    isinstance(target, ast.Name)
                    and isinstance(value, ast.Subscript)
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "Literal"
                ):
                    names.add(target.id)
    return frozenset(names)


#: (path, class-or-function, field) -> why this one is a fixed vocabulary.
_FINITE_STATE_FIELDS: dict[tuple[str, str, str], str] = {
    ("src/fpstune/settings/base.py", "SettingExecutor", "category"): "a setting's category",
    ("src/fpstune/settings/base.py", "SettingExecutor", "value_type"): "a setting's value kind",
    ("src/fpstune/settings/base.py", "SettingExecutor", "evidence_level"): "C1's evidence ladder",
    ("src/fpstune/settings/base.py", "SettingExecutor", "risk_level"): "the risk taxonomy",
    ("src/fpstune/settings/base.py", "SettingExecutor", "scope"): "essential/recommended/complete",
    ("src/fpstune/settings/base.py", "SettingExecutor", "detect_type"): "how detection runs",
    ("src/fpstune/settings/base.py", "SettingExecutor", "apply_type"): "how the write runs",
    ("src/fpstune/api/schemas.py", "SettingDefinitionResponse", "category"): "serialized as-is",
    ("src/fpstune/api/schemas.py", "SettingDefinitionResponse", "value_type"): "serialized as-is",
    ("src/fpstune/api/schemas.py", "SettingDefinitionResponse", "evidence_level"): "C1's ladder",
    ("src/fpstune/api/schemas.py", "SettingDefinitionResponse", "risk_level"): "the risk taxonomy",
    ("src/fpstune/api/schemas.py", "SettingDefinitionResponse", "scope"): "scope is three words",
    ("src/fpstune/api/schemas.py", "SettingDefinitionResponse", "domain"): "three pages own a row",
    ("src/fpstune/api/schemas.py", "DetectRequest", "category"): "parsed once at the boundary",
    ("src/fpstune/benchmark/verify_round.py", "Verdict", "status"): "a verdict has five answers",
    ("src/fpstune/settings/cleanup_measure.py", "CleanupSize", "status"): "four readings, no fifth",
    ("src/fpstune/utils/self_check.py", "Finding", "area"): "three areas, no fourth",
    ("src/fpstune/safety/restore.py", "RestoreOutcome", "kind"): "six outcomes, no seventh",
    ("src/fpstune/settings/executors/steam_config.py", "vdf_path", "scope"): "two Steam files",
}


@functools.cache
def _annotations() -> dict[tuple[str, str, str], ast.expr]:
    """Every annotation of a class field or a named function argument, keyed by path/owner/name."""
    found: dict[tuple[str, str, str], ast.expr] = {}
    for path in _source_files():
        tree = _tree(path)
        relative = _relative(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (
                        isinstance(item, ast.AnnAssign)
                        and isinstance(item.target, ast.Name)
                        and item.annotation is not None
                    ):
                        found[(relative, node.name, item.target.id)] = item.annotation
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in (*node.args.args, *node.args.kwonlyargs):
                    if arg.annotation is not None:
                        found[(relative, node.name, arg.arg)] = arg.annotation
    return found


def _is_finite(annotation: ast.expr, finite_names: set[str]) -> bool:
    text = ast.unparse(annotation).replace("| None", "").strip()
    if text.startswith("Literal["):
        return True
    return text in finite_names


class TestIllegalStatesAreUnrepresentable:
    """P-ILLEGAL: a value with a fixed vocabulary has a type that says so.

    Every field pinned here held one of a handful of strings documented in a
    comment. A comment is not a type: a fourth spelling reaches the UI as a state
    nothing renders, and nothing fails until a user sees it.
    """

    def test_pinned_fields_are_finite_state_typed(self) -> None:
        annotations = _annotations()
        finite_names = _finite_type_names()
        offenders = []
        for key in _FINITE_STATE_FIELDS:
            annotation = annotations.get(key)
            if annotation is None:
                offenders.append(f"{key[0]}::{key[1]}.{key[2]} is gone")
            elif not _is_finite(annotation, finite_names):
                offenders.append(f"{key[0]}::{key[1]}.{key[2]} is {ast.unparse(annotation)}")
        assert not offenders, (
            "a finite-state field is typed as an open string — give it a Literal or "
            "a StrEnum: " + "; ".join(offenders)
        )

    def test_the_pinned_list_is_not_stale(self) -> None:
        annotations = _annotations()
        stale = [key for key in _FINITE_STATE_FIELDS if key not in annotations]
        assert not stale, (
            "the pinned finite-state list names fields that no longer exist — update "
            "it in the same change: " + "; ".join(f"{p}::{o}.{n}" for p, o, n in stale)
        )


# === P-PARSE / P-POLA =======================================================


@functools.cache
def _project_model_names() -> frozenset[str]:
    """Classes in the tree that are pydantic models (directly or through a project model)."""
    models: set[str] = set()
    per_file: dict[Path, dict[str, ast.ClassDef]] = {}
    for path in _source_files():
        tree = _tree(path)
        per_file[path] = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }
    changed = True
    while changed:
        changed = False
        for classes in per_file.values():
            for name, node in classes.items():
                if name in models:
                    continue
                for base in node.bases:
                    base_name = ast.unparse(base)
                    if base_name in {"BaseModel", "pydantic.BaseModel"} or base_name in models:
                        models.add(name)
                        changed = True
                        break
    return frozenset(models)


class TestParsingHappensAtTheBoundary:
    """P-PARSE/P-POLA: the request body is parsed into a typed model, once.

    A route that reads `request.json()` itself re-validates at the wrong layer
    and makes the shape of the wire format a second, invisible contract. FastAPI
    already parses a declared model; the test keeps every handler on that path.
    """

    _ROUTE_FILES = tuple(sorted((SRC / "api" / "routes").glob("*.py"))) + (SRC / "api" / "main.py",)

    def _route_functions(self) -> list[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]]:
        found = []
        for path in self._ROUTE_FILES:
            tree = _tree(path)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if any(ast.unparse(d).startswith("router.") for d in node.decorator_list):
                    found.append((path, node))
        return found

    def test_no_route_parses_the_raw_request_itself(self) -> None:
        offenders = []
        for path, node in self._route_functions():
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                func = child.func
                if not isinstance(func, ast.Attribute):
                    continue
                receiver = ast.unparse(func.value)
                if func.attr in {"json", "body", "form", "stream"} and receiver.endswith("request"):
                    offenders.append(f"{_relative(path)}:{child.lineno}: {ast.unparse(child)}")
        assert not offenders, (
            "a route parses the raw request itself — declare a pydantic body instead: "
            + "; ".join(offenders)
        )

    def test_route_bodies_are_typed_project_models(self) -> None:
        models = _project_model_names()
        offenders = []
        for path, node in self._route_functions():
            for arg in node.args.args:
                if arg.arg != "request" or arg.annotation is None:
                    continue
                annotation = ast.unparse(arg.annotation)
                if annotation not in models:
                    offenders.append(f"{_relative(path)}:{node.lineno}: request: {annotation}")
        assert not offenders, (
            "a route takes a request body that is not a project pydantic model — a raw "
            "Request hands parsing back to the handler: " + "; ".join(offenders)
        )


# === P-CQS / P-POLA =========================================================

_QUERY_PREFIXES = (
    "get_",
    "read_",
    "detect_",
    "list_",
    "find_",
    "query_",
    "is_",
    "has_",
    "status",
    "check_",
    "count_",
)

_WRITE_ATTRIBUTES = {
    "write_text",
    "write_bytes",
    "mkdir",
    "unlink",
    "rename",
    "replace",
    "rmdir",
    "touch",
    "SetValue",
    "SetValueEx",
    "CreateKey",
    "CreateKeyEx",
    "DeleteKey",
    "DeleteValue",
    "DeleteKeyEx",
}

#: (path, function) -> reason a read-named function is allowed to write. Empty:
#: every query-named function in the tree is a query today.
_ALLOWED_QUERY_WRITES: dict[tuple[str, str], str] = {}


@functools.cache
def _query_writes() -> tuple[tuple[str, str, int, str], ...]:
    offenders: list[tuple[str, str, int, str]] = []
    for path in _source_files():
        tree = _tree(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith(_QUERY_PREFIXES):
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                func = child.func
                if isinstance(func, ast.Attribute) and func.attr in _WRITE_ATTRIBUTES:
                    offenders.append((_relative(path), node.name, child.lineno, ast.unparse(func)))
                if isinstance(func, ast.Name) and func.id == "open":
                    mode = ""
                    if len(child.args) > 1 and isinstance(child.args[1], ast.Constant):
                        mode = str(child.args[1].value)
                    for keyword in child.keywords:
                        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                            mode = str(keyword.value.value)
                    if any(char in mode for char in "wax+"):
                        offenders.append(
                            (_relative(path), node.name, child.lineno, f"open({mode!r})")
                        )
    return tuple(offenders)


class TestQueryFunctionsDoNotWrite:
    """P-CQS/P-POLA: a function named `get_`/`read_`/`check_` reads; it does not write.

    The one real finding this gate made was `check_build_change`, which rewrote
    the build record while its name promised a comparison; it is now
    `compare_and_record_build`. The allowlist is empty and can only shrink.
    """

    def test_no_query_named_function_writes(self) -> None:
        offenders = [
            f"{path}::{name}:{line}: {call}"
            for path, name, line, call in _query_writes()
            if (path, name) not in _ALLOWED_QUERY_WRITES
        ]
        assert not offenders, (
            "a read-named function writes — rename it to say what it does, or split the "
            "write out: " + "; ".join(offenders)
        )

    def test_every_allowance_still_matches(self) -> None:
        found = {(path, name) for path, name, _line, _call in _query_writes()}
        stale = [
            f"{path}::{name}" for path, name in _ALLOWED_QUERY_WRITES if (path, name) not in found
        ]
        assert not stale, (
            "a query-write allowance no longer matches anything — delete it: " + "; ".join(stale)
        )


# === P-EXPLICIT =============================================================

_BLIND_EXCEPTIONS = {"Exception", "BaseException"}


def _is_reraise(handler: ast.ExceptHandler) -> bool:
    """Whether the handler ends by re-raising: a cleanup, not a swallow."""
    return bool(handler.body) and isinstance(handler.body[-1], ast.Raise)


def _logs_the_exception(handler: ast.ExceptHandler) -> bool:
    """Whether the handler records the exception with its traceback.

    This is the same line ruff draws for BLE001: `logger.exception(...)` and
    `logger.<level>(..., exc_info=True)` keep the information, so the catch is
    not blind even though its type is broad.
    """
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "exception":
            return True
        for keyword in node.keywords:
            if keyword.arg == "exc_info" and isinstance(keyword.value, ast.Constant):
                return keyword.value.value is True
    return False


def _has_noqa(line: str, code: str) -> bool:
    return bool(re.search(rf"#\s*noqa:\s*[A-Z0-9,\s]*\b{code}\b", line))


def _handler_line(path: Path, handler: ast.ExceptHandler) -> str:
    lines = _source(path)
    return lines[handler.lineno - 1] if handler.lineno - 1 < len(lines) else ""


def _try_line(path: Path, node: ast.Try) -> str:
    lines = _source(path)
    return lines[node.lineno - 1] if node.lineno - 1 < len(lines) else ""


class TestExplicitFailures:
    """P-EXPLICIT: a broad catch is a decision, and the decision is written down.

    The tree has dozens of broad catches that are correct — a hardware probe on
    an unknown machine must answer "not detected", a background measurement must
    not take the API down — and every one of them either records the exception
    with its traceback or says why in a `# noqa: BLE001 - <reason>` comment. This
    test is the binding while the ruff select that enforces it is pending: a new
    bare `except Exception:` that neither re-raises nor logs fails here.
    """

    def test_every_broad_catch_says_why(self) -> None:
        offenders = []
        for path in _source_files():
            tree = _tree(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler) or node.type is None:
                    continue
                if ast.unparse(node.type) not in _BLIND_EXCEPTIONS:
                    continue
                if _is_reraise(node) or _logs_the_exception(node):
                    continue
                line = _handler_line(path, node)
                if not _has_noqa(line, "BLE001"):
                    offenders.append(f"{_relative(path)}:{node.lineno}: {line.strip()}")
        assert not offenders, (
            "a broad catch without a reason — narrow it, log it with `exc_info=True`, "
            "or add `# noqa: BLE001 - <why this catch is the right width>`: " + "; ".join(offenders)
        )

    def test_no_silent_try_except_pass(self) -> None:
        """S110's shape: a blind catch whose whole body is `pass`."""
        offenders = []
        for path in _source_files():
            tree = _tree(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try):
                    continue
                for handler in node.handlers:
                    if len(handler.body) != 1 or not isinstance(handler.body[0], ast.Pass):
                        continue
                    caught = ast.unparse(handler.type) if handler.type is not None else "bare"
                    if caught not in _BLIND_EXCEPTIONS and caught != "bare":
                        continue
                    if _has_noqa(_handler_line(path, handler), "S110") or _has_noqa(
                        _try_line(path, node), "S110"
                    ):
                        continue
                    offenders.append(
                        f"{_relative(path)}:{handler.lineno}: {_handler_line(path, handler).strip()}"
                    )
        assert not offenders, (
            "a swallowed exception with no explanation — log it, or add "
            "`# noqa: S110 - <why nothing can be said>`: " + "; ".join(offenders)
        )
