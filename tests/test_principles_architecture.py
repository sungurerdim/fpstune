"""Catalogue section A applied to the backend: dependency direction and tree shape.

`CLAUDE.md` says what the product is; the catalogue says how the code should be
built. This file is the part of the catalogue that can be checked by reading the
tree, so it is checked by reading the tree — no subprocess, no import of the app.

What it binds:

- **P-DIP / P-SOC / P-SRP / P-COHESION** — `.importlinter` is the enforced layer
  order. The config cannot test itself, so the tests here compare it against the
  Python constants below (the intended order and every exception with its
  reason), and prove each exception still matches a real import. An exception
  can therefore only shrink: deleting the import without deleting the entry, or
  adding an entry without adding the import, is red.
- **P-COMPOSE** — no project class inherits through another project class into a
  chain. One level is composition with a named base; two is a hierarchy nobody
  chose deliberately.
- **P-ISP** — the one interface the docs call "deliberately three methods" stays
  three methods.
- **P-LSP** — no subclass of a project class replaces inherited behaviour with
  `NotImplementedError`, and every concrete executor implements the two abstract
  methods its base declares.
- **P-FCIS** — the modules the docs call pure (the bulk planner, the verdict
  judge) import no IO module and write nothing.
- **P-SOC (framework confinement)** — the two forbidden contracts are declared,
  so the HTTP framework stays in `api/` and the CLI framework in `commands/`.
"""

from __future__ import annotations

import ast
import configparser
import functools
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "fpstune"
CONFIG = ROOT / ".importlinter"


@functools.cache
def _source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


@functools.cache
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


@functools.cache
def _parse_config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(CONFIG.read_text(encoding="utf-8"))
    return parser


def _contract(name: str) -> configparser.SectionProxy:
    return _parse_config()[f"importlinter:contract:{name}"]


# The intended dependency direction, highest layer first. This is the Python copy
# of the order `.importlinter` enforces; the test compares the two, so a reorder
# is an edit in both places rather than one file quietly disagreeing with the
# other. The comments are the reason each layer sits where it does.
_LAYERS = (
    "fpstune.commands",  # the CLI: presentation and orchestration over everything
    "fpstune.api",  # HTTP routes and their schemas
    "fpstune.safety",  # restore points: a write-time service
    "fpstune.health",  # read-only diagnosis, which composes instruments
    "fpstune.benchmark",  # instruments: measure and report, never change settings
    "fpstune.settings",  # registry, definitions, executors, detection
    "fpstune.core",  # OS integrations: DISM, NVAPI sessions, the DRS key table
    "fpstune.utils",  # infrastructure: winapi, logger, paths, process watching
)

# Every import the layers contract ignores, with the reason it cannot point down.
# Keys are exactly the `importer -> imported` expressions in `.importlinter`.
_LAYERING_EXCEPTIONS = {
    "fpstune.settings.performance_headroom -> fpstune.benchmark.gpu_scene": (
        "measure_now() is the UI's 'measure this machine now' path and it runs the scene"
    ),
    "fpstune.settings.performance_headroom -> fpstune.benchmark.operation_lock": (
        "measure_now() holds the one operation mutex while the scene runs"
    ),
    "fpstune.settings.performance_headroom -> fpstune.benchmark.suite": (
        "type annotation only: the band is recorded from a BenchResult, never built here"
    ),
    "fpstune.utils.operation_log -> fpstune.settings.base": (
        "type annotation only: the log names the setting it logs, never applies one"
    ),
}

# The exceptions above that exist only for a type annotation, erased at runtime.
_TYPE_ONLY_EXCEPTIONS = {
    "fpstune.settings.performance_headroom -> fpstune.benchmark.suite",
    "fpstune.utils.operation_log -> fpstune.settings.base",
}


@functools.cache
def _module_path(module: str) -> Path:
    """The file a dotted `fpstune` module lives in."""
    parts = module.split(".")
    assert parts[0] == "fpstune", f"not a project module: {module}"
    base = SRC.joinpath(*parts[1:])
    return base.with_suffix(".py") if base.with_suffix(".py").is_file() else base / "__init__.py"


class _ImportSite:
    """One import statement, and whether it is type-only or inside a function."""

    def __init__(self, line: int, type_only: bool, lazy: bool) -> None:
        self.line = line
        self.type_only = type_only
        self.lazy = lazy


@functools.cache
def _import_sites(module: str, target: str) -> tuple[_ImportSite, ...]:
    """Every import in `module` that resolves to `target` or one of its members."""
    path = _module_path(module)
    tree = _tree(path)
    sites: list[_ImportSite] = []

    def matches(name: str | None) -> bool:
        return bool(name) and (name == target or name.startswith(target + "."))

    def is_type_checking(node: ast.If) -> bool:
        test = node.test
        return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )

    def walk(node: ast.AST, *, type_ctx: int, depth: int) -> None:
        if isinstance(node, ast.ImportFrom) and matches(node.module):
            sites.append(_ImportSite(node.lineno, type_ctx > 0, depth > 0))
        if isinstance(node, ast.Import) and any(matches(alias.name) for alias in node.names):
            sites.append(_ImportSite(node.lineno, type_ctx > 0, depth > 0))
        if isinstance(node, ast.If) and is_type_checking(node):
            for child in node.body:
                walk(child, type_ctx=type_ctx + 1, depth=depth)
            for child in node.orelse:
                walk(child, type_ctx=type_ctx, depth=depth)
            return
        child_depth = (
            depth + 1 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else depth
        )
        for child in ast.iter_child_nodes(node):
            walk(child, type_ctx=type_ctx, depth=child_depth)

    walk(tree, type_ctx=0, depth=0)
    return tuple(sites)


class TestLayeringContract:
    """P-DIP/P-SOC: imports point down, and every exception is a named decision."""

    def test_the_layers_are_the_intended_order(self) -> None:
        declared = [line.strip() for line in _contract("layering")["layers"].splitlines()]
        declared = [line for line in declared if line]
        assert declared == list(_LAYERS), (
            "the layer order in .importlinter and the recorded intention disagree — "
            "change both, or one of them is describing an architecture nobody chose"
        )

    def test_every_layer_is_a_real_package(self) -> None:
        missing = [layer for layer in _LAYERS if not _module_path(layer).is_file()]
        assert not missing, f"layers in the contract do not exist in the tree: {missing}"

    def test_the_exception_list_is_exactly_the_recorded_one(self) -> None:
        declared = {
            line.strip()
            for line in _contract("layering")["ignore_imports"].splitlines()
            if line.strip()
        }
        assert declared == set(_LAYERING_EXCEPTIONS), (
            "the layering exceptions and their recorded reasons disagree. A new "
            "exception needs a reason here; a removed one must leave this map in "
            "the same change, so the list can only shrink."
        )

    def test_every_exception_still_matches_a_real_import(self) -> None:
        stale = []
        for expression in _LAYERING_EXCEPTIONS:
            importer, imported = (part.strip() for part in expression.split("->"))
            sites = _import_sites(importer, imported)
            if not sites:
                stale.append(f"{expression} (no such import)")
        assert not stale, (
            "the layering contract exempts imports that no longer exist — delete "
            "the exception so the exception list stays honest: " + "; ".join(stale)
        )

    def test_type_only_exceptions_are_type_only(self) -> None:
        offenders = []
        for expression in _TYPE_ONLY_EXCEPTIONS:
            importer, imported = (part.strip() for part in expression.split("->"))
            runtime = [site for site in _import_sites(importer, imported) if not site.type_only]
            if runtime:
                offenders.append(
                    f"{expression} imports at runtime (line {runtime[0].line}) — "
                    "it is not a type-only exception"
                )
        assert not offenders, "; ".join(offenders)

    def test_the_framework_contracts_are_declared(self) -> None:
        """P-SOC: the presentation frameworks stay in their own layer."""
        parser = _parse_config()
        contracts = {
            section for section in parser.sections() if section.startswith("importlinter:")
        }
        assert "importlinter:contract:http-framework" in contracts, (
            "the contract that keeps fastapi/uvicorn out of the domain layers is gone"
        )
        assert "importlinter:contract:cli-framework" in contracts, (
            "the contract that keeps click out of the domain layers is gone"
        )


@functools.cache
def _class_index() -> _ClassIndex:
    return _ClassIndex()


class _ClassIndex:
    """Project classes by name, and the module each one was defined in."""

    def __init__(self) -> None:
        self.by_name: dict[str, list[tuple[Path, ast.ClassDef]]] = {}
        self.by_file: dict[Path, dict[str, ast.ClassDef]] = {}
        for path in _source_files():
            tree = _tree(path)
            local = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
            self.by_file[path] = local
            for name, node in local.items():
                self.by_name.setdefault(name, []).append((path, node))

    def resolve(self, name: str, path: Path) -> tuple[Path, ast.ClassDef] | None:
        """The project class `name` means at `path`: same file first, then unambiguous."""
        local = self.by_file[path].get(name)
        if local is not None:
            return path, local
        candidates = self.by_name.get(name, [])
        return candidates[0] if len(candidates) == 1 else None

    def project_ancestors(self, path: Path, node: ast.ClassDef) -> list[str]:
        chain: list[str] = []
        seen = {node.name}
        current_path, current = path, node
        while True:
            nxt = None
            for base in current.bases:
                if not isinstance(base, ast.Name):
                    continue
                resolved = self.resolve(base.id, current_path)
                if resolved is None or base.id in seen:
                    continue
                nxt = resolved
                break
            if nxt is None:
                return chain
            current_path, current = nxt
            seen.add(current.name)
            chain.append(current.name)


class TestInheritanceDepth:
    """P-COMPOSE: a project class may sit on one project base, not on a chain.

    `BaseExecutor` and its six executors, `ConfigValueRejected` and the two
    game-config rejections: one project level each, which is a named base class.
    A third level is a hierarchy — behaviour assembled by inheritance instead of
    composition — and this gate makes the author say so in the allowlist.
    """

    _MAX_PROJECT_ANCESTORS = 1

    #: (path, class) -> allowed depth, for a chain that is genuinely wanted. Empty:
    #: every project hierarchy is flat today, so a new one is red on arrival.
    _ALLOWED: dict[tuple[str, str], int] = {}

    def _depths(self) -> dict[tuple[str, str], int]:
        index = _class_index()
        found: dict[tuple[str, str], int] = {}
        for path in _source_files():
            for name, node in index.by_file[path].items():
                depth = len(index.project_ancestors(path, node))
                if depth:
                    found[(_relative(path), name)] = depth
        return found

    def test_no_project_class_inherits_through_another_project_class(self) -> None:
        offenders = [
            f"{path}::{name} sits on {depth} project base(s)"
            for (path, name), depth in self._depths().items()
            if depth > self._ALLOWED.get((path, name), self._MAX_PROJECT_ANCESTORS)
        ]
        assert not offenders, (
            "inheritance deeper than one project base — compose instead, or add an "
            "allowlist entry with the reason: " + "; ".join(offenders)
        )

    def test_the_allowlist_is_not_stale(self) -> None:
        depths = self._depths()
        stale = [
            f"{path}::{name}: now {depths.get((path, name), 0)}, allowed {allowed}"
            for (path, name), allowed in self._ALLOWED.items()
            if depths.get((path, name), 0) < allowed
        ]
        assert not stale, (
            "an inheritance allowance is no longer needed — remove it so the "
            "allowlist can only shrink: " + "; ".join(stale)
        )


class TestLiskovSubstitution:
    """P-LSP: an override keeps the base's contract.

    A subclass that answers `NotImplementedError` is a subtype you cannot use
    where the base was promised; a concrete executor that does not implement the
    two abstract methods would be one too, and ABC only catches it at
    instantiation.
    """

    def test_no_project_subclass_raises_not_implemented(self) -> None:
        index = _class_index()
        offenders = []
        for path in _source_files():
            for name, node in index.by_file[path].items():
                if not index.project_ancestors(path, node):
                    continue
                for item in node.body:
                    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    raises = any(
                        isinstance(child, ast.Raise)
                        and isinstance(child.exc, ast.Name)
                        and child.exc.id == "NotImplementedError"
                        for child in ast.walk(item)
                    )
                    if raises:
                        offenders.append(f"{_relative(path)}::{name}.{item.name}")
        assert not offenders, (
            "a subclass replaces inherited behaviour with NotImplementedError — "
            "split the base or make the method abstract there: " + "; ".join(offenders)
        )

    def test_every_executor_implements_both_abstract_methods(self) -> None:
        index = _class_index()
        offenders = []
        for path in _source_files():
            for name, node in index.by_file[path].items():
                if "BaseExecutor" not in index.project_ancestors(path, node):
                    continue
                defined = {
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                missing = {"detect", "apply"} - defined
                if missing:
                    offenders.append(f"{_relative(path)}::{name} lacks {sorted(missing)}")
        assert not offenders, (
            "a concrete executor relies on inheriting an abstract method: " + "; ".join(offenders)
        )


class TestInterfaceSegregation:
    """P-ISP: a discoverer can do exactly what it needs, through a narrow protocol."""

    def test_the_registrar_protocol_stays_three_methods(self) -> None:
        tree = _tree(SRC / "settings" / "discovery" / "__init__.py")
        registrar = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "Registrar"
        )
        members = {
            item.name
            for item in registrar.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert members == {"register", "get", "get_all"}, (
            "the Registrar protocol grew past the three things a discoverer may do "
            f"({sorted(members)}) — a discoverer that needs more wants a probe, not "
            "a wider registry"
        )


class TestPureCore:
    """P-FCIS: the planners and judges are calculations; IO stays at the edge.

    Both modules are described in the project map as pure, and both are called on
    paths where a stray subprocess or file write would make the answer depend on
    the machine rather than on its inputs.
    """

    _PURE_MODULES = {
        "settings/bulk_plan.py": "the bulk lane planner: settings in, lanes out",
        "benchmark/verify_round.py": "the verdict judge: claim + measurement in, verdict out",
    }

    _IO_MODULES = {
        "subprocess",
        "ctypes",
        "winreg",
        "socket",
        "shutil",
        "tempfile",
        "urllib",
        "http",
        "requests",
        "asyncio",
    }

    _WRITE_CALLS = {
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
    }

    def test_pure_modules_import_no_io_module(self) -> None:
        offenders = []
        for relative in self._PURE_MODULES:
            tree = _tree(SRC / relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split(".")[0]]
                else:
                    continue
                for name in names:
                    if name in self._IO_MODULES:
                        offenders.append(f"{relative}: imports {name}")
        assert not offenders, "a module the project map calls pure reached for IO: " + "; ".join(
            offenders
        )

    def test_pure_modules_do_not_write(self) -> None:
        offenders = []
        for relative in self._PURE_MODULES:
            tree = _tree(SRC / relative)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in self._WRITE_CALLS:
                    offenders.append(f"{relative}:{node.lineno}: {ast.unparse(func)}")
                if isinstance(func, ast.Name) and func.id == "open":
                    mode = ""
                    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                        mode = str(node.args[1].value)
                    for keyword in node.keywords:
                        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                            mode = str(keyword.value.value)
                    if any(char in mode for char in "wax+"):
                        offenders.append(f"{relative}:{node.lineno}: open({mode!r})")
        assert not offenders, "a module the project map calls pure writes something: " + "; ".join(
            offenders
        )
