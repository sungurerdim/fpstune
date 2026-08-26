"""The quality gates, run rather than read.

`CLAUDE.md` is the contract every setting and every PR is judged against, and it
was judged by reading — which means a rule whose binding has been renamed away
still reads as enforced. That is the worst failure mode a rules document has: it
looks stricter than the repository actually is, and nobody finds out until
someone leans on a guard that stopped existing.

Two kinds of check live here.

*The bindings resolve.* C11 ends in a table of "this rule is enforced by that
test", and a table like that is worth nothing the first time a file moves.

*C4 and C9 actually run.* Both shipped as shell one-liners in the document, and
both were wrong in a way only running them reveals: C4's bracket expression
matched byte-by-byte under this shell, so `✓`, `°` and `±` came back as Turkish
letters, and C9's had no way to exclude the test fixtures its own prose declares
legitimate. A gate nobody can run clean is a gate everybody learns to ignore.

Deliberately not asserted: what the rules *say*. Prose is for humans, and pinning
it would turn every wording improvement into a test failure.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Where a path named in the document may live. The document writes paths the way
# a reader wants them — `applicability.py`, `api/routes/settings.py` — rather
# than repo-relative, so a reference matches any file whose path ends with it.
_SEARCH_ROOTS = ("src", "frontend/src", "tests", "scripts", ".github")

_SKIP_DIRS = {"__pycache__", "node_modules", ".venv", "venv", "dist", ".ruff_cache"}

# Named in the rules, absent from the tree on purpose. Not exceptions to the
# guard so much as the guard knowing what these three are:
#   tasks.md          the in-flight plan artifact — gitignored, deleted when the
#                     work lands, so a clean checkout has never had one
#   ds/audit/*        dev-skill scratch output, gitignored for the same reason
#   headroom.json     written at runtime under ~/.fpstune, not shipped
_NOT_IN_THE_TREE = {"tasks.md", "ds/audit/findings.md", "headroom.json"}

_PATH_REFERENCE = re.compile(
    r"`([A-Za-z0-9_./-]+\.(?:py|ts|tsx|md|json|yml|yaml))(::[A-Za-z0-9_]+)?`"
)


@pytest.fixture(scope="module")
def rules() -> str:
    """`CLAUDE.md` with fenced blocks removed.

    The project map is a fenced tree of bare filenames rendered for reading, not
    a list of assertions; only prose references are bindings.
    """
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def _files_under(roots: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not any(part in _SKIP_DIRS for part in path.parts):
                found.append(path)
    return found


@pytest.fixture(scope="module")
def tree() -> list[str]:
    """Every candidate file, as a forward-slash path relative to the repo root."""
    paths = [p.relative_to(ROOT).as_posix() for p in _files_under(_SEARCH_ROOTS)]
    paths += [p.name for p in ROOT.glob("*.*") if p.is_file()]
    return paths


def _resolves(reference: str, tree: list[str]) -> bool:
    return any(candidate == reference or candidate.endswith("/" + reference) for candidate in tree)


class TestTheRulesPointAtCodeThatExists:
    def test_every_file_the_rules_name_is_in_the_tree(self, rules: str, tree: list[str]) -> None:
        """A renamed module leaves the rule that cites it reading as enforced."""
        named = {match.group(1) for match in _PATH_REFERENCE.finditer(rules)}
        missing = sorted(ref for ref in named - _NOT_IN_THE_TREE if not _resolves(ref, tree))

        assert not missing, (
            f"CLAUDE.md cites files that do not exist: {missing}. Either the rule "
            "moved and the citation did not, or the rule is describing something "
            "that was never written."
        )

    def test_every_test_the_rules_name_as_proof_exists(self, rules: str) -> None:
        """`path::name` in the rules is a claim that a specific guard is in place.

        C4, C9, C11's binding table and the shared-file lock invariant all cite
        one, and a citation is only worth something if the thing it names is
        still there under that name. Either a test function or the class holding
        a group of them counts — both are how a gate is cited in practice.
        """
        for match in _PATH_REFERENCE.finditer(rules):
            suffix = match.group(2)
            if suffix is None:
                continue
            path, name = ROOT / match.group(1), suffix.lstrip(":")
            assert path.exists(), f"CLAUDE.md cites {match.group(1)}, which is gone"
            source = path.read_text(encoding="utf-8")
            assert re.search(rf"^\s*(?:def|class) {re.escape(name)}\b", source, re.MULTILINE), (
                f"CLAUDE.md names {name} in {match.group(1)} as the proof of a rule, "
                "and nothing by that name is defined there"
            )


class TestTheGatesAreCounted:
    def test_the_heading_states_how_many_gates_there_are(self, rules: str) -> None:
        """C10 was added once without the heading following; it read "9 Quality
        Gates" over ten of them, which is exactly how a gate goes unnoticed."""
        heading = re.search(r"^## (\d+) Quality Gates", rules, flags=re.MULTILINE)
        gates = re.findall(r"^### (C\d+) —", rules, flags=re.MULTILINE)

        assert heading, "the quality-gate heading is gone"
        assert int(heading.group(1)) == len(gates), (
            f"the heading says {heading.group(1)} gates, the document defines {len(gates)}: {gates}"
        )

    def test_the_gates_are_numbered_without_a_hole(self, rules: str) -> None:
        """Gates are cited by number in PRs and commit messages, so a skipped or
        reused number makes every one of those citations ambiguous."""
        numbers = [int(g[1:]) for g in re.findall(r"^### (C\d+) —", rules, flags=re.MULTILINE)]
        assert numbers == list(range(1, len(numbers) + 1)), numbers


# Every source file C4 and C9 police: the shipped product, not the tests around
# it. `tests/` deliberately carries this machine's panel name and localised
# strings as fixture input, which is what makes it a fixture.
_SHIPPED = ("src", "frontend/src")

_TURKISH_LETTERS = frozenset("çğıİöşüÇĞÖŞÜ")

# Documentation quoting what Windows printed back is evidence, not prose.
# `ping.exe` and `ValidDisplayValues` both answer in the system language, and
# these are the exact strings a Turkish install returned — which is the entire
# reason each code path reads a numeric status enum instead of the text.
# Deleting the quote to satisfy a grep would delete the finding that justifies
# the code. Matched on the full quoted phrase so the permission covers the
# evidence and nothing else in the file.
_QUOTED_OS_OUTPUT = {
    ("src/fpstune/utils/path_mtu.py", '"Paketin parçalanması gerekiyor"'),
    ("src/fpstune/settings/definitions/network.py", '"1.0 Gbps Tam İkili"'),
    ("src/fpstune/api/hardware/network_adapters.py", '"Radyo türü"'),
}


def _shipped_sources() -> list[Path]:
    return [
        path
        for path in _files_under(_SHIPPED)
        if path.suffix in {".py", ".ts", ".tsx"} and ".test." not in path.name
    ]


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith(("#", "//", "*"))


class TestC4EnglishOnly:
    """The documented one-liner could not answer this question.

    `grep -rn "[çğıİöşüÇĞÖŞÜ]"` matches bytes under this shell, so every `✓`,
    `°` and `±` in the benchmark output came back as a Turkish letter and the
    gate reported ten hits it had no business reporting. Nobody can act on a
    gate that cries wolf, so the check moved here where the comparison is over
    characters.
    """

    def test_no_shipped_source_carries_a_turkish_letter(self) -> None:
        offenders: list[str] = []
        for path in _shipped_sources():
            relative = path.relative_to(ROOT).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not _TURKISH_LETTERS & set(line):
                    continue
                if any(relative == where and quote in line for where, quote in _QUOTED_OS_OUTPUT):
                    continue
                offenders.append(f"{relative}:{number}: {line.strip()}")

        assert not offenders, "C4: non-English text in shipped source:\n" + "\n".join(offenders)

    def test_the_carve_out_does_not_outlive_the_lines_it_names(self) -> None:
        """An exception list is how a gate rots. If one of these quotes is
        paraphrased into English, its entry has to go with it — otherwise the
        file keeps a permission that no longer protects anything."""
        for relative, quote in _QUOTED_OS_OUTPUT:
            source = (ROOT / relative).read_text(encoding="utf-8")
            assert quote in source, (
                f"C4 carve-out for {relative} names {quote}, which is no longer "
                "in the file — delete the entry"
            )


class TestC9MachineNeutral:
    """Nothing about the developer's machine or account reaches shipped source.

    The literals are the ones that actually shipped once: this panel's model, a
    Battle.net profile id, a localised games directory, this laptop's GPU and
    CPU, and any hardcoded user profile path.
    """

    # Each scrubbed literal is spelled with a character class so this file never
    # contains the literal itself — the history scrub requires zero tree-wide
    # hits, and the regex engine reads the two spellings identically.
    _MACHINE_LITERALS = re.compile(
        r"Q25G4[S]|41613607[3]|Oyunla[r]|RTX 307[0]|i7-11800[H]|Users\\[A-Za-z]"
    )

    def test_no_shipped_source_names_this_machine(self) -> None:
        offenders: list[str] = []
        for path in _shipped_sources():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                # A comment explaining *why* a code path exists may name the
                # hardware that forced it. The document says so; the shell
                # version had no way to also spare the test fixtures, which is
                # why `MonitorCard.test.tsx` failed a gate it never violated.
                if _is_comment(line):
                    continue
                if self._MACHINE_LITERALS.search(line):
                    offenders.append(
                        f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()}"
                    )

        assert not offenders, "C9: shipped source names this machine:\n" + "\n".join(offenders)


class TestB6NoAssumedDeviceCapability:
    """C9's sibling for capabilities: no constant where the device publishes the value.

    C9 keeps the developer's *machine* out of the source; this gate keeps the
    developer's *assumptions about hardware* out. Every pattern below is a value
    some device publishes about itself — VRAM size, a driver's stock buffer
    count, the CPU's core topology, the panel's refresh rate — that shipped as
    a constant instead, and each constant was wrong on real hardware.

    The known offenders are frozen as a baseline of exact per-file counts. A
    new occurrence anywhere is red immediately. Fixing one leaves its baseline
    entry stale, which is also red — the entry must be deleted in the same
    change, so the shrink is visible in the diff and the baseline can never
    grow back silently (the C4 carve-out's does-not-outlive discipline).
    """

    # (name, pattern, why the device's own answer is required, {file: count})
    # Issue codes refer to the tracker's epic map (B6 is the gate itself).
    _ASSUMED: tuple[tuple[str, re.Pattern[str], str, dict[str, int]], ...] = (
        (
            "adapter_ram_as_vram",
            re.compile(r"AdapterRAM"),
            "Win32_VideoController.AdapterRAM is a 32-bit field that clamps at "
            "4 GB; VRAM comes from HardwareInformation.qwMemorySize or DXGI "
            "DedicatedVideoMemory (A7, fixed — the baseline entry is gone)",
            {},
        ),
        (
            "buffer_default_constant",
            re.compile(r"NumericParameterMinValue,\s*256"),
            "the driver publishes its stock buffer count as "
            "DefaultRegistryValue; writing 256 makes reset write a value that "
            "was never this driver's default (B1, fixed — the baseline entry "
            "is gone)",
            {},
        ),
        (
            "rss_base_core_constant",
            re.compile(r"'optimized'\) \{ 2 \}"),
            "the driver publishes *RssBaseProcNumber min/max/default and "
            "Get-NetAdapterRSS publishes MaxProcessorNumber; on a hybrid CPU "
            "logical processor 2 may be an E-core (B2)",
            {"src/fpstune/settings/definitions/network.py": 1},
        ),
        (
            "panel_refresh_fallback",
            re.compile(r"\(60, False\)"),
            "settings/panel.py is the one panel derivation and its rule is "
            "that an unknown rate stays 0 and never becomes 60 (B5, fixed — "
            "the baseline entry is gone)",
            {},
        ),
    )

    def test_assumed_capability_baseline_only_shrinks(self) -> None:
        problems: list[str] = []
        for name, pattern, why, baseline in self._ASSUMED:
            observed: dict[str, int] = {}
            for path in _shipped_sources():
                count = sum(
                    len(pattern.findall(line))
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if not _is_comment(line)
                )
                if count:
                    observed[path.relative_to(ROOT).as_posix()] = count
            for file, count in sorted(observed.items()):
                allowed = baseline.get(file, 0)
                if count > allowed:
                    problems.append(
                        f"B6 [{name}]: {file} has {count} occurrence(s), baseline "
                        f"allows {allowed} — {why}"
                    )
            for file, allowed in sorted(baseline.items()):
                if observed.get(file, 0) < allowed:
                    problems.append(
                        f"B6 [{name}]: baseline grants {file} {allowed} "
                        f"occurrence(s) but only {observed.get(file, 0)} remain — "
                        "the fix landed, delete the stale entry"
                    )

        assert not problems, "\n".join(problems)
