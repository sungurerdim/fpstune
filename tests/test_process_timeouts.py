"""Gate: no child process is ended by a fixed clock outside the stall rule.

`fpstune.utils.process_watch` (`StallPolicy`: QUERY / CHANGE / SERVICING, and
`run` / `run_watched`) is the one place a process's lifetime is judged: a run ends
on *silence*, never on a duration. Nine fixes (21ab879, 994f5d4, 8322bfc, 412414f,
46660eb, ...) replaced per-command ceilings that killed healthy work — a 30 s
restore point cut mid-snapshot, a 60 s cache cleanup cut mid-delete on a machine
with 15 GB to remove. A clean machine and a neglected one differ by orders of
magnitude for the same command, so no constant covers both.

This scans every module under `src/fpstune` for a process call that carries its
own clock:

* `subprocess.run/call/check_call/check_output/Popen(..., timeout=...)`
* `.communicate(...)` / `.wait(...)` with a timeout on a process-shaped receiver
  (assigned from `subprocess.Popen`, or named process/proc/popen/child)
* a PowerShell / watched-run helper handed any `timeout` / `deadline` keyword

`process_watch.py` is the SSOT and is skipped. A wait that is legitimately
bounded is listed in `ALLOWED` with the reason it is not the bug class, keyed by
file and enclosing function so a line shift does not break it; an entry that no
longer matches a site fails too, so the list cannot rot into blanket permission.
Thread joins, `Event.wait`, sockets and HTTP timeouts are not process lifetimes
and are not scanned.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "fpstune"
SSOT = "utils/process_watch.py"

SUBPROCESS_FUNCS = frozenset({"run", "call", "check_call", "check_output", "Popen"})
WATCHED_HELPERS = frozenset(
    {
        "run_powershell",
        "run_powershell_stream",
        "_run_powershell_async",
        "run_watched",
    }
)
PROCESS_HINTS = ("process", "proc", "popen", "child")

# (file relative to src/fpstune, enclosing function) -> why it is not the bug class.
ALLOWED: dict[tuple[str, str], str] = {
    (
        "benchmark/presentmon.py",
        "PresentMonBenchmark.terminate_child",
    ): "grace after process.kill(): the work is already abandoned and nothing is left to cut short",
    (
        "benchmark/presentmon.py",
        "PresentMonBenchmark.stop_capture",
    ): "grace after terminate()/kill() on a capture the caller has already decided to end",
    (
        "benchmark/presentmon.py",
        "PresentMonBenchmark.wait_for_capture",
    ): "a `--timed N --terminate_after_timed` capture has a duration the caller chose; the wait is that duration plus margin, and a miss only returns False",
}


def _enclosing(tree: ast.Module) -> dict[int, str]:
    """Map every call node id to its dotted class/function scope."""
    scopes: dict[int, str] = {}

    def visit(node: ast.AST, scope: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            inner = scope
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = [*scope, child.name]
            if isinstance(child, ast.Call):
                scopes[id(child)] = ".".join(scope) or "<module>"
            visit(child, inner)

    visit(tree, [])
    return scopes


def _popen_targets(tree: ast.Module) -> set[str]:
    """Names and attributes the module assigns a `subprocess.Popen(...)` to."""
    targets: set[str] = set()
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Assign):
            value, names = node.value, node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            value, names = node.value, [node.target]
        if isinstance(value, ast.Call) and ast.unparse(value.func) in ("subprocess.Popen", "Popen"):
            targets.update(ast.unparse(name) for name in names)
    return targets


def _imported_from_subprocess(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            names.update(a.asname or a.name for a in node.names if a.name in SUBPROCESS_FUNCS)
    return names


def _has_clock_kw(call: ast.Call) -> bool:
    return any(kw.arg and ("timeout" in kw.arg or "deadline" in kw.arg) for kw in call.keywords)


def find_process_clocks(source: str) -> list[tuple[int, str, str]]:
    """Every process call in `source` that carries its own clock.

    Returns (line, enclosing scope, what was seen).
    """
    tree = ast.parse(source)
    scopes = _enclosing(tree)
    popen_targets = _popen_targets(tree)
    bare = _imported_from_subprocess(tree)
    found: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        text = ast.unparse(func)
        what = None
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
            and func.attr in SUBPROCESS_FUNCS
            and _has_clock_kw(node)
        ):
            what = f"{text}(timeout=...)"
        if isinstance(func, ast.Name) and func.id in bare and _has_clock_kw(node):
            what = f"{text}(timeout=...)"
        if isinstance(func, ast.Attribute) and func.attr in ("communicate", "wait"):
            receiver = ast.unparse(func.value)
            leaf = receiver.rsplit(".", 1)[-1].lower()
            process_shaped = receiver in popen_targets or any(h in leaf for h in PROCESS_HINTS)
            # communicate(input, timeout) takes its timeout second; wait(timeout) first.
            positional = len(node.args) >= (2 if func.attr == "communicate" else 1)
            has_timeout = _has_clock_kw(node) or positional
            if has_timeout and (process_shaped or func.attr == "communicate"):
                what = f"{text}(timeout)"
        helper = text.rsplit(".", 1)[-1]
        if helper in WATCHED_HELPERS and _has_clock_kw(node):
            what = f"{text}(timeout=...)"
        if what:
            found.append((node.lineno, scopes.get(id(node), "<module>"), what))
    return sorted(found)


def _scan_tree() -> list[tuple[str, int, str, str]]:
    hits = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(SRC_ROOT).as_posix()
        if rel == SSOT:
            continue
        for line, scope, what in find_process_clocks(path.read_text(encoding="utf-8")):
            hits.append((rel, line, scope, what))
    return hits


def test_no_process_is_ended_by_a_fixed_clock_outside_the_stall_rule() -> None:
    """A literal clock on a child process belongs to `process_watch`, not the caller."""
    offenders = [
        f"{SRC_ROOT.name}/{rel}:{line}: {what} in {scope} — run it under "
        f"fpstune.utils.process_watch (a StallPolicy), or add it to ALLOWED with the "
        f"reason it is bounded by design"
        for rel, line, scope, what in _scan_tree()
        if (rel, scope) not in ALLOWED
    ]
    assert not offenders, "\n" + "\n".join(offenders)


def test_every_allowed_wait_still_exists() -> None:
    """A stale ALLOWED entry would pre-approve whatever lands in that function next."""
    seen = {(rel, scope) for rel, _, scope, _ in _scan_tree()}
    stale = sorted(set(ALLOWED) - seen)
    assert not stale, f"ALLOWED entries matching no process clock (remove them): {stale}"


def test_every_allowed_wait_states_its_reason() -> None:
    assert all(len(reason) > 20 for reason in ALLOWED.values())


# --- the scanner itself: each shape the nine fixes removed, plus what it must leave alone ---


def test_scanner_flags_the_shapes_the_fixes_removed() -> None:
    """Red-proof for the gate: a clock on every spelling a process can be given one."""
    source = """
import subprocess
from subprocess import check_output

def a(cmd):
    return subprocess.run(cmd, capture_output=True, timeout=30)

def b(cmd):
    return check_output(cmd, timeout=60)

def c(cmd):
    proc = subprocess.Popen(cmd)
    proc.wait(timeout=120)

def d(self, cmd):
    self._p = subprocess.Popen(cmd)
    self._p.wait(5)

def e(child):
    child.communicate(timeout=10)

def f(command):
    return run_powershell(command, timeout=30)
"""
    hits = {(scope, what) for _, scope, what in find_process_clocks(source)}
    assert hits == {
        ("a", "subprocess.run(timeout=...)"),
        ("b", "check_output(timeout=...)"),
        ("c", "proc.wait(timeout)"),
        ("d", "self._p.wait(timeout)"),
        ("e", "child.communicate(timeout)"),
        ("f", "run_powershell(timeout=...)"),
    }


def test_scanner_leaves_non_process_waits_alone() -> None:
    """Threads, events, sockets and HTTP are not a process's lifetime."""
    source = """
import threading, urllib.request

def g(worker, ready, request):
    worker.join(timeout=5)
    ready.wait(timeout=30)
    urllib.request.urlopen(request, timeout=10)

def h(proc):
    proc.wait()
    return proc.communicate()
"""
    assert find_process_clocks(source) == []
