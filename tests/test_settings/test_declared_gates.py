"""`min_os_build` and `driver_gate` are declared on the setting and checked once.

A build or driver rule used to live wherever its author put it: a free-form
`min_windows_build` key in a conditions dict, a constant in one definition file
compared inside its own helper. Fields on `SettingExecutor`, evaluated by
`ApplicabilityChecker.is_applicable` and nowhere else, make "below the gate" one
answer — `is_applicable=False` with a reason — on every surface.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from fpstune.settings.applicability import ApplicabilityChecker, HardwareContext
from fpstune.settings.base import (
    DriverGate,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
    parse_driver_version,
    version_at_least,
)
from fpstune.settings.hardware_context import comparable_driver_version
from fpstune.settings.registry import SettingsRegistry

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "fpstune"


def _setting(**gates: object) -> SettingExecutor:
    return SettingExecutor(
        id="test:gated",
        category=SettingCategory.GPU,
        display_name="Gated",
        description="A setting that only exists to carry a gate.",
        value_type=SettingValueType.BOOL,
        **gates,  # type: ignore[arg-type]
    )


def _context(
    *, build: int = 26100, vendor: str | None = "nvidia", driver: str | None = "576.80"
) -> HardwareContext:
    return HardwareContext(
        gpu_vendor=vendor,
        gpu_vendors=[vendor] if vendor else [],
        gpu_driver_version=driver,
        windows_build=build,
    )


class TestMinOsBuild:
    def test_below_the_floor_is_not_applicable_and_names_it(self) -> None:
        setting = _setting(min_os_build=22000)
        assert ApplicabilityChecker(_context(build=19045)).is_applicable(setting) == (
            False,
            "Requires Windows build 22000+",
        )

    def test_exactly_at_the_floor_is_applicable(self) -> None:
        setting = _setting(min_os_build=22000)
        assert ApplicabilityChecker(_context(build=22000)).is_applicable(setting) == (True, "")

    def test_above_the_floor_is_applicable(self) -> None:
        setting = _setting(min_os_build=22000)
        assert ApplicabilityChecker(_context(build=26200)).is_applicable(setting) == (True, "")

    def test_an_unreadable_build_holds_back_rather_than_assuming_the_newest_windows(self) -> None:
        """`build_hardware_context` turns a non-numeric build into 0, which fails every floor."""
        setting = _setting(min_os_build=22000)
        assert ApplicabilityChecker(_context(build=0)).is_applicable(setting)[0] is False

    def test_no_gate_declared_is_always_applicable(self) -> None:
        assert ApplicabilityChecker(_context(build=0, driver=None)).is_applicable(_setting()) == (
            True,
            "",
        )


class TestDriverGate:
    def test_below_the_minimum_is_not_applicable_and_names_it(self) -> None:
        setting = _setting(driver_gate=DriverGate("nvidia", min_version="576.80"))
        assert ApplicabilityChecker(_context(driver="572.16")).is_applicable(setting) == (
            False,
            "Requires NVIDIA driver 576.80+",
        )

    def test_at_the_minimum_is_applicable(self) -> None:
        setting = _setting(driver_gate=DriverGate("nvidia", min_version="576.80"))
        assert ApplicabilityChecker(_context(driver="576.80")).is_applicable(setting) == (True, "")

    def test_above_the_maximum_is_not_applicable_and_names_it(self) -> None:
        setting = _setting(driver_gate=DriverGate("nvidia", max_version="566.36"))
        assert ApplicabilityChecker(_context(driver="576.80")).is_applicable(setting) == (
            False,
            "Requires NVIDIA driver 566.36 or earlier",
        )

    def test_a_version_compares_by_number_not_by_text(self) -> None:
        """`591.9` sorts after `591.59` as text; as numbers it is the older driver."""
        setting = _setting(driver_gate=DriverGate("nvidia", min_version="591.59"))
        assert ApplicabilityChecker(_context(driver="591.9")).is_applicable(setting)[0] is False
        assert ApplicabilityChecker(_context(driver="1000.1")).is_applicable(setting)[0] is True

    def test_unknown_driver_version_holds_back_and_says_it_is_unknown_not_old(self) -> None:
        """Not guessed: an unread driver is neither inside nor outside the range.

        Held back because a setting a driver rejects costs more than one a user
        briefly cannot see; the reason names the unknown so it is not read as an
        absent feature.
        """
        setting = _setting(driver_gate=DriverGate("nvidia", min_version="576.80"))
        for unread in (None, "", "Unknown", "576.80-beta"):
            ok, reason = ApplicabilityChecker(_context(driver=unread)).is_applicable(setting)
            assert ok is False, unread
            assert "could not be read" in reason, (unread, reason)

    def test_another_vendors_gpu_is_out_of_range(self) -> None:
        setting = _setting(driver_gate=DriverGate("nvidia", min_version="576.80"))
        assert ApplicabilityChecker(_context(vendor="amd", driver="32.0.15.7602")).is_applicable(
            setting
        ) == (False, "Requires NVIDIA GPU")

    def test_no_gpu_at_all_is_out_of_range(self) -> None:
        setting = _setting(driver_gate=DriverGate("amd", min_version="32.0.0.0"))
        assert ApplicabilityChecker(_context(vendor=None, driver=None)).is_applicable(setting) == (
            False,
            "Requires AMD GPU",
        )

    def test_windows_form_versions_compare_for_amd_and_intel(self) -> None:
        setting = _setting(driver_gate=DriverGate("amd", min_version="32.0.15.7602"))
        old = _context(vendor="amd", driver="32.0.15.6014")
        new = _context(vendor="amd", driver="32.0.21.1000")
        assert ApplicabilityChecker(old).is_applicable(setting)[0] is False
        assert ApplicabilityChecker(new).is_applicable(setting) == (True, "")


class TestDriverGateDeclarationIsValidatedAtRegistryBuild:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"vendor": "matrox", "min_version": "1.0"},
            {"vendor": "nvidia"},
            {"vendor": "nvidia", "min_version": "576.x"},
            {"vendor": "nvidia", "min_version": "600.0", "max_version": "576.80"},
        ],
        ids=["unknown-vendor", "no-bound", "not-dotted-numbers", "empty-range"],
    )
    def test_a_malformed_gate_raises_when_declared(self, kwargs: dict[str, str]) -> None:
        with pytest.raises(ValueError):
            DriverGate(**kwargs)


class TestComparableDriverVersion:
    def test_nvidia_smi_number_is_already_comparable(self) -> None:
        assert comparable_driver_version("nvidia", "591.59") == "591.59"

    def test_nvidia_windows_form_becomes_the_marketing_number(self) -> None:
        """The WMI fallback reports 32.0.15.9159 for what nvidia-smi calls 591.59."""
        assert comparable_driver_version("nvidia", "32.0.15.9159") == "591.59"
        assert comparable_driver_version("nvidia", "31.0.15.3623") == "536.23"

    def test_amd_and_intel_keep_windows_form(self) -> None:
        assert comparable_driver_version("amd", "32.0.15.7602") == "32.0.15.7602"
        assert comparable_driver_version("intel", "31.0.101.5186") == "31.0.101.5186"

    @pytest.mark.parametrize("unread", [None, "", "Unknown", "n/a"])
    def test_an_unreadable_version_is_none_not_a_guess(self, unread: str | None) -> None:
        assert comparable_driver_version("nvidia", unread) is None


class TestVersionArithmetic:
    def test_padding_makes_a_short_version_equal_its_zero_extension(self) -> None:
        assert version_at_least((576, 80), (576, 80, 0))
        assert version_at_least((576, 80, 0), (576, 80))

    def test_parse_rejects_anything_not_digits_and_dots(self) -> None:
        assert parse_driver_version("32.0.15.7602") == (32, 0, 15, 7602)
        assert parse_driver_version("") is None
        assert parse_driver_version("1..2") is None


class TestEveryBuildOrDriverRuleIsDeclared:
    """The grep the issue asked for, kept as a test so an ad-hoc check cannot return."""

    def test_the_old_condition_keys_are_gone_from_every_setting(self) -> None:
        for setting in SettingsRegistry(discover_dynamic=False).get_all():
            keys = set(setting.applicable_conditions or {})
            assert not keys & {"min_windows_build", "max_windows_build"}, setting.id

    def test_a_shipped_setting_declares_its_floor_as_a_field(self) -> None:
        floors = {
            s.id: s.min_os_build
            for s in SettingsRegistry(discover_dynamic=False).get_all()
            if s.min_os_build is not None
        }
        assert floors, "no shipped setting declares min_os_build; this guard would prove nothing"

    def test_only_the_checker_and_the_context_read_the_windows_build(self) -> None:
        """No definition compares the build itself; the one check is the applicability checker.

        `windows_build` is read in `applicability.py` (the check) and written in
        `hardware_context.py` (the probe); a definition or an executor reading it
        is a second, ad-hoc check.
        """
        allowed = {"applicability.py", "hardware_context.py"}
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            if path.name in allowed or "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                name = (
                    node.attr
                    if isinstance(node, ast.Attribute)
                    else node.arg
                    if isinstance(node, ast.keyword)
                    else None
                )
                if name == "windows_build":
                    offenders.append(
                        f"{path.relative_to(SRC).as_posix()}:{getattr(node, 'lineno', 0)}"
                    )
        assert not offenders, f"windows_build read outside the applicability check: {offenders}"


class TestOnlyKnownPlacesCompareTheBuild:
    """Every ordered comparison of a Windows build number, and why it is allowed.

    A build floor that decides *applicability* is `min_os_build`, checked in
    `ApplicabilityChecker`. Two other comparisons are not gates and stay, each
    named here: the OS probe classifying itself (Windows 10 / 11, supported
    floor), and MPO's `_mpo_values`, where the build selects which registry
    values one always-applicable setting writes (see the comment above
    `_MPO_BOTH_VALUES_BUILD` for why that cannot be a declared gate).
    """

    ALLOWED = {
        ("settings/applicability.py", "_declared_gates"),
        ("utils/detect.py", "is_supported"),
        ("utils/detect.py", "get_os_info"),
        ("settings/definitions/display.py", "_mpo_values"),
    }

    @staticmethod
    def _enclosing(tree: ast.AST) -> dict[ast.AST, str]:
        owner: dict[ast.AST, str] = {}
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                for node in ast.walk(fn):
                    owner[node] = fn.name  # innermost wins: nested defs walk later
        return owner

    def _comparisons(self) -> set[tuple[str, str]]:
        found: set[tuple[str, str]] = set()
        for path in SRC.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            owner = self._enclosing(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                if not any(isinstance(op, ast.Gt | ast.GtE | ast.Lt | ast.LtE) for op in node.ops):
                    continue
                if "build" in ast.unparse(node).lower():
                    found.add((path.relative_to(SRC).as_posix(), owner.get(node, "<module>")))
        return found

    def test_no_build_comparison_exists_outside_the_named_places(self) -> None:
        unknown = self._comparisons() - self.ALLOWED
        assert not unknown, (
            f"ad-hoc Windows-build comparison, declare it or name it here: {unknown}"
        )

    def test_every_named_place_still_compares_a_build(self) -> None:
        """An allow-list entry whose comparison is gone is stale and must go too."""
        stale = self.ALLOWED - self._comparisons()
        assert not stale, f"allow-listed but no longer comparing a build: {stale}"
