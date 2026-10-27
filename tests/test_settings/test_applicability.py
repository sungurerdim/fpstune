"""Tests for settings applicability checks and values_equal comparison."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fpstune.settings.applicability import (
    ABSENT_READINGS,
    ALREADY_AT_HARDWARE_DEFAULT,
    HYBRID_GPU_CLASSIFY_PS,
    NOT_AVAILABLE,
    NOT_FOUND,
    NOT_INSTALLED,
    NOT_SUPPORTED,
    ApplicabilityChecker,
    HardwareContext,
    absent_reason,
    classify_gpu_adapters,
    is_absent_reading,
    values_equal,
)
from fpstune.settings.base import DetectType, DriverGate


def _setting(conditions: dict | None = None, **overrides: object) -> MagicMock:
    """A setting double whose declared gates are explicit, never auto-mocked.

    A bare MagicMock answers every attribute, and `_declared_gates` decides with
    `isinstance` — an auto-mocked `min_os_build` is not an int and a
    `driver_gate` is not a DriverGate, so both would silently read as "no gate".
    """
    setting = MagicMock()
    setting.applicable_conditions = {} if conditions is None else conditions
    setting.min_os_build = None
    setting.driver_gate = None
    setting.is_service = False
    for name, value in overrides.items():
        setattr(setting, name, value)
    return setting


class TestValuesEqual:
    """Tests for values_equal() — critical for verify logic (Criterion 6)."""

    # --- None handling ---

    def test_both_none_are_equal(self) -> None:
        """Both None should be considered equal."""
        assert values_equal(None, None) is True

    def test_none_vs_value_not_equal(self) -> None:
        """None vs any non-None value should be unequal."""
        assert values_equal(None, "enabled") is False
        assert values_equal("enabled", None) is False
        assert values_equal(None, 0) is False
        assert values_equal(0, None) is False

    # --- String comparison (case-insensitive) ---

    def test_identical_strings(self) -> None:
        """Exact same strings should be equal."""
        assert values_equal("enabled", "enabled") is True

    def test_case_insensitive_strings(self) -> None:
        """String comparison should be case-insensitive."""
        assert values_equal("Enabled", "enabled") is True
        assert values_equal("DISABLED", "disabled") is True
        assert values_equal("Yes", "YES") is True

    def test_different_strings(self) -> None:
        """Different string values should be unequal."""
        assert values_equal("enabled", "disabled") is False

    def test_empty_strings(self) -> None:
        """Empty strings should be equal to each other."""
        assert values_equal("", "") is True

    def test_string_vs_empty_string(self) -> None:
        """Non-empty string vs empty string should be unequal."""
        assert values_equal("enabled", "") is False

    # --- Integer comparison ---

    def test_equal_integers(self) -> None:
        """Same integers should be equal."""
        assert values_equal(8, 8) is True
        assert values_equal(0, 0) is True

    def test_different_integers(self) -> None:
        """Different integers should be unequal."""
        assert values_equal(8, 6) is False

    def test_negative_integers(self) -> None:
        """Negative integers should compare correctly."""
        assert values_equal(-1, -1) is True
        assert values_equal(-1, 1) is False

    # --- Float comparison with tolerance ---

    def test_exact_floats(self) -> None:
        """Exact float values should be equal."""
        assert values_equal(0.5, 0.5) is True

    def test_float_within_tolerance(self) -> None:
        """Floats within 0.001 tolerance should be equal."""
        assert values_equal(0.5, 0.5005) is True
        assert values_equal(0.5, 0.4995) is True

    def test_float_outside_tolerance(self) -> None:
        """Floats outside 0.001 tolerance should be unequal."""
        assert values_equal(0.5, 0.502) is False
        assert values_equal(0.5, 0.498) is False

    def test_int_vs_float_equal(self) -> None:
        """Integer 0 and float 0.0 should be equal."""
        assert values_equal(0, 0.0) is True
        assert values_equal(1, 1.0) is True

    def test_int_vs_float_different(self) -> None:
        """Integer 1 and float 1.5 should be unequal."""
        assert values_equal(1, 1.5) is False

    # --- Boolean comparison ---

    def test_equal_booleans(self) -> None:
        """Same booleans should be equal."""
        assert values_equal(True, True) is True
        assert values_equal(False, False) is True

    def test_different_booleans(self) -> None:
        """Different booleans should be unequal."""
        assert values_equal(True, False) is False

    # --- Cross-type coercion (numeric strings ↔ int/float) ---

    def test_numeric_string_vs_int(self) -> None:
        """String '1' must equal int 1 after coercion."""
        assert values_equal("1", 1) is True
        assert values_equal("0", 0) is True
        assert values_equal("42", 42) is True

    def test_numeric_string_mismatch(self) -> None:
        """String '2' must not equal int 1."""
        assert values_equal("2", 1) is False

    # --- Whitespace / CRLF normalization ---

    def test_crlf_normalized(self) -> None:
        """CRLF-terminated string must equal its LF counterpart."""
        assert values_equal("yes\r\n", "yes") is True
        assert values_equal("enabled\r\n", "enabled") is True

    def test_leading_trailing_whitespace(self) -> None:
        """Surrounding whitespace must be stripped before comparison."""
        assert values_equal(" enabled ", "Enabled") is True
        assert values_equal("  1  ", 1) is True

    def test_list_equality(self) -> None:
        """Lists should use direct comparison."""
        assert values_equal([1, 2, 3], [1, 2, 3]) is True
        assert values_equal([1, 2], [2, 1]) is False

    # --- Boundary values ---

    def test_large_integers(self) -> None:
        """Large integers (e.g., registry DWORD max) should compare correctly."""
        assert values_equal(4294967295, 4294967295) is True
        assert values_equal(4294967295, 4294967294) is False

    def test_float_precision_boundary(self) -> None:
        """Values at the 0.001 boundary — IEEE 754 representation matters."""
        # 1.001 - 1.0 in IEEE 754 is ~0.000999... (< 0.001), so values_equal returns True
        assert values_equal(1.0, 1.001) is True
        # 1.002 - 1.0 = 0.002 which is clearly > 0.001
        assert values_equal(1.0, 1.002) is False
        # Just under 0.001 apart — should be equal
        assert values_equal(1.0, 1.0009) is True


class TestHardwareContext:
    """Tests for HardwareContext dataclass."""

    def test_default_values(self) -> None:
        """Default HardwareContext should have safe defaults."""
        ctx = HardwareContext()
        assert ctx.cpu_vendor is None
        assert ctx.gpu_vendor is None
        assert ctx.gpu_vendors == []
        assert ctx.windows_build == 0
        assert ctx.is_admin is False
        assert ctx.features == set()
        # None, not False: an unprobed machine has not answered "no VRR panel".
        assert ctx.has_vrr_monitor is None

    def test_to_dict_preserves_all_fields(self) -> None:
        """to_dict() should include all fields."""
        ctx = HardwareContext(
            cpu_vendor="intel",
            gpu_vendor="nvidia",
            gpu_vendors=["nvidia"],
            gpu_name="RTX 4080",
            windows_build=22631,
            windows_version="23H2",
            is_windows_11=True,
            is_admin=True,
            features={"docker", "hyper_v"},
            has_vrr_monitor=True,
        )
        d = ctx.to_dict()
        assert d["cpu_vendor"] == "intel"
        assert d["gpu_vendor"] == "nvidia"
        assert d["gpu_name"] == "RTX 4080"
        assert d["windows_build"] == 22631
        assert d["is_admin"] is True
        assert set(d["features"]) == {"docker", "hyper_v"}
        assert d["has_vrr_monitor"] is True

    def test_to_dict_features_is_list(self) -> None:
        """to_dict() should convert features set to list (JSON-serializable)."""
        ctx = HardwareContext(features={"a", "b"})
        d = ctx.to_dict()
        assert isinstance(d["features"], list)


class TestApplicabilityChecker:
    """Tests for ApplicabilityChecker condition evaluation."""

    @pytest.fixture
    def nvidia_intel_context(self) -> HardwareContext:
        """Context with NVIDIA GPU and Intel CPU on Windows 11."""
        return HardwareContext(
            cpu_vendor="intel",
            gpu_vendor="nvidia",
            gpu_vendors=["nvidia"],
            windows_build=22631,
            is_windows_11=True,
            is_admin=True,
            features={"docker"},
        )

    @pytest.fixture
    def amd_context(self) -> HardwareContext:
        """Context with AMD GPU and AMD CPU."""
        return HardwareContext(
            cpu_vendor="amd",
            gpu_vendor="amd",
            gpu_vendors=["amd"],
            windows_build=22621,
            is_windows_11=True,
            is_admin=True,
        )

    def _make_setting(self, conditions: dict) -> object:
        """Create a minimal mock setting with applicable_conditions."""
        from unittest.mock import MagicMock

        setting = MagicMock()
        setting.applicable_conditions = conditions
        return setting

    def test_no_conditions_always_applicable(self, nvidia_intel_context: HardwareContext) -> None:
        """Settings with no conditions should always be applicable."""
        checker = ApplicabilityChecker(nvidia_intel_context)
        setting = self._make_setting({})
        is_applicable, reason = checker.is_applicable(setting)
        assert is_applicable is True
        assert reason == ""

    def test_vrr_unknown_and_vrr_absent_give_different_reasons(self) -> None:
        """ "Could not read the panels" is a fact about detection, not hardware.

        The two states used to collapse: a failed monitor probe set
        has_vrr_monitor=False, so every VRR-dependent setting reported
        "Requires G-Sync/FreeSync/VRR compatible monitor" as if the panels had
        answered — the exact confusion A11 exists to remove.
        """
        setting = self._make_setting({"requires_vrr": True})

        unknown = ApplicabilityChecker(HardwareContext(has_vrr_monitor=None))
        applicable, reason = unknown.is_applicable(setting)
        assert applicable is False
        assert "unknown" in reason
        assert "Requires" not in reason

        absent = ApplicabilityChecker(HardwareContext(has_vrr_monitor=False))
        applicable, reason = absent.is_applicable(setting)
        assert applicable is False
        assert reason == "Requires G-Sync/FreeSync/VRR compatible monitor"

        present = ApplicabilityChecker(HardwareContext(has_vrr_monitor=True))
        applicable, reason = present.is_applicable(setting)
        assert applicable is True

    def test_cpu_vendor_match(self, nvidia_intel_context: HardwareContext) -> None:
        """Setting requiring Intel CPU should match Intel context."""
        checker = ApplicabilityChecker(nvidia_intel_context)
        setting = self._make_setting({"cpu_vendor": "intel"})
        is_applicable, _ = checker.is_applicable(setting)
        assert is_applicable is True

    def test_cpu_vendor_mismatch(self, nvidia_intel_context: HardwareContext) -> None:
        """Setting requiring AMD CPU should reject Intel context."""
        checker = ApplicabilityChecker(nvidia_intel_context)
        setting = self._make_setting({"cpu_vendor": "amd"})
        is_applicable, reason = checker.is_applicable(setting)
        assert is_applicable is False
        assert "AMD" in reason

    def test_gpu_vendor_match(self, nvidia_intel_context: HardwareContext) -> None:
        """Setting requiring NVIDIA GPU should match NVIDIA context."""
        checker = ApplicabilityChecker(nvidia_intel_context)
        setting = self._make_setting({"gpu_vendor": "nvidia"})
        is_applicable, _ = checker.is_applicable(setting)
        assert is_applicable is True

    def test_gpu_vendor_mismatch(self, nvidia_intel_context: HardwareContext) -> None:
        """Setting requiring AMD GPU should reject NVIDIA context."""
        checker = ApplicabilityChecker(nvidia_intel_context)
        setting = self._make_setting({"gpu_vendor": "amd"})
        is_applicable, reason = checker.is_applicable(setting)
        assert is_applicable is False
        assert "AMD" in reason

    def test_gpu_vendor_none_rejects(self) -> None:
        """Setting requiring GPU should reject when no GPU detected."""
        ctx = HardwareContext(gpu_vendor=None)
        checker = ApplicabilityChecker(ctx)
        setting = self._make_setting({"gpu_vendor": "nvidia"})
        is_applicable, _ = checker.is_applicable(setting)
        assert is_applicable is False

    def test_feature_present(self, nvidia_intel_context: HardwareContext) -> None:
        """Setting requiring 'docker' feature should match when docker detected."""
        checker = ApplicabilityChecker(nvidia_intel_context)
        setting = self._make_setting({"feature": "docker"})
        is_applicable, _ = checker.is_applicable(setting)
        assert is_applicable is True

    def test_feature_absent_check(self, nvidia_intel_context: HardwareContext) -> None:
        """feature_absent='docker' should reject when docker IS present."""
        checker = ApplicabilityChecker(nvidia_intel_context)
        setting = self._make_setting({"feature_absent": "docker"})
        is_applicable, _ = checker.is_applicable(setting)
        assert is_applicable is False

    def test_feature_absent_passes_when_missing(self, amd_context: HardwareContext) -> None:
        """feature_absent='docker' should pass when docker is NOT present."""
        checker = ApplicabilityChecker(amd_context)
        setting = self._make_setting({"feature_absent": "docker"})
        is_applicable, _ = checker.is_applicable(setting)
        assert is_applicable is True

    def test_min_os_build(self, nvidia_intel_context: HardwareContext) -> None:
        """A setting whose min_os_build the machine meets stays on offer."""
        checker = ApplicabilityChecker(nvidia_intel_context)  # build 22631
        setting = self._make_setting({})
        setting.min_os_build = 22000
        assert checker.is_applicable(setting) == (True, "")

    def test_min_os_build_too_low(self, nvidia_intel_context: HardwareContext) -> None:
        """A setting whose min_os_build is above the machine's build is not applicable."""
        checker = ApplicabilityChecker(nvidia_intel_context)  # build 22631
        setting = self._make_setting({})
        setting.min_os_build = 99999
        assert checker.is_applicable(setting) == (False, "Requires Windows build 99999+")

    def test_requires_admin_when_admin(self, nvidia_intel_context: HardwareContext) -> None:
        """Setting requiring admin should pass when running as admin."""
        checker = ApplicabilityChecker(nvidia_intel_context)
        setting = self._make_setting({"requires_admin": True})
        is_applicable, _ = checker.is_applicable(setting)
        assert is_applicable is True

    def test_requires_admin_when_not_admin(self) -> None:
        """Setting requiring admin should reject when not admin."""
        ctx = HardwareContext(is_admin=False)
        checker = ApplicabilityChecker(ctx)
        setting = self._make_setting({"requires_admin": True})
        is_applicable, reason = checker.is_applicable(setting)
        assert is_applicable is False
        assert "admin" in reason.lower()


class TestAnticheatFactReachesTheUser:
    """H8: the one anti-cheat fact rides in the setting's own risk_warning.

    `check_anticheat_compatibility` had no caller and `has_anticheat_games`
    was never True, so the warning could never render. Decided: delete the
    dead checker and carry the fact where the row already shows warnings.
    """

    def test_low_latency_names_the_ultra_risk_in_its_own_copy(self) -> None:
        from fpstune.settings.definitions.gpu import NVIDIA_LOW_LATENCY

        warning = NVIDIA_LOW_LATENCY.risk_warning or ""
        assert "anti-cheat" in warning and "ultra" in warning.lower()

    def test_the_dead_checker_stayed_dead(self) -> None:
        import fpstune.settings.applicability as module

        assert not hasattr(module, "ANTICHEAT_WARNINGS")
        assert not hasattr(module.ApplicabilityChecker, "check_anticheat_compatibility")


class TestAbsentReadingVocabulary:
    """The one spelling set, and the explanation that accompanies it."""

    def test_the_sentinels_are_exactly_the_documented_spellings(self) -> None:
        assert (
            NOT_SUPPORTED,
            NOT_FOUND,
            NOT_AVAILABLE,
            NOT_INSTALLED,
            ALREADY_AT_HARDWARE_DEFAULT,
        ) == (
            "not_supported",
            "not_found",
            "not_available",
            "not_installed",
            "already_at_hardware_default",
        )
        assert (
            frozenset(
                {
                    NOT_SUPPORTED,
                    NOT_FOUND,
                    NOT_AVAILABLE,
                    NOT_INSTALLED,
                    ALREADY_AT_HARDWARE_DEFAULT,
                }
            )
            == ABSENT_READINGS
        )

    def test_is_absent_reading_strips_and_lowercases(self) -> None:
        assert is_absent_reading("  NOT_SUPPORTED\r\n") is True
        assert is_absent_reading("Already_At_Hardware_Default") is True
        assert is_absent_reading("enabled") is False
        assert is_absent_reading(None) is False
        assert is_absent_reading(1) is False
        assert is_absent_reading(["not_found"]) is False

    def test_absent_reason_names_the_three_states(self) -> None:
        assert (
            absent_reason(reading=" already_at_hardware_default\r\n")
            == "The driver already ships this tuned: nothing to change on this device"
        )
        service = _setting(is_service=True)
        assert absent_reason(service) == "Service not installed on this system"
        plain = _setting(is_service=False)
        assert absent_reason(plain) == "Feature not available on this system"
        assert absent_reason() == "Feature not available on this system"


class TestGpuAdapterClassification:
    """Integrated/discrete from the PCI vendor IDs, never from a model name."""

    def test_intel_is_integrated_and_nvidia_discrete(self) -> None:
        adapters = [r"PCI\VEN_8086&DEV_46A6", r"PCI\VEN_10DE&DEV_2684"]
        assert classify_gpu_adapters(adapters) == (True, True)

    def test_amd_alone_is_discrete_not_integrated(self) -> None:
        assert classify_gpu_adapters([r"PCI\VEN_1002&DEV_744C"]) == (False, True)

    def test_an_intel_arc_alone_is_not_a_hybrid(self) -> None:
        assert classify_gpu_adapters([r"PCI\VEN_8086&DEV_56A0"]) == (True, False)

    def test_unknown_and_empty_adapters_are_neither(self) -> None:
        assert classify_gpu_adapters([]) == (False, False)
        assert classify_gpu_adapters([r"PCI\VEN_ABCD&DEV_0001"]) == (False, False)

    def test_the_powershell_probe_uses_the_same_vendor_ids(self) -> None:
        assert "VEN_8086&" in HYBRID_GPU_CLASSIFY_PS
        assert "VEN_10DE&" in HYBRID_GPU_CLASSIFY_PS
        assert "VEN_1002&" in HYBRID_GPU_CLASSIFY_PS
        assert "$igpu" in HYBRID_GPU_CLASSIFY_PS
        assert "$dgpu" in HYBRID_GPU_CLASSIFY_PS


class TestHardwareContextDefaults:
    """Every default is the safe answer, and to_dict carries every field."""

    def test_every_field_default_is_the_safe_one(self) -> None:
        ctx = HardwareContext()
        assert ctx.cpu_vendor is None
        assert ctx.gpu_vendor is None
        assert ctx.gpu_vendors == []
        assert ctx.gpu_name is None
        assert ctx.gpu_driver_version is None
        assert ctx.windows_build == 0
        assert ctx.windows_version == ""
        assert ctx.is_windows_11 is False
        assert ctx.is_admin is False
        assert ctx.features == set()
        assert ctx.feature_labels == {}
        assert ctx.has_vrr_monitor is None
        assert ctx.ucpd_guard_up is False

    def test_to_dict_carries_every_field(self) -> None:
        ctx = HardwareContext(
            cpu_vendor="amd",
            gpu_vendor="nvidia",
            gpu_vendors=["nvidia", "intel"],
            gpu_name="X",
            gpu_driver_version="576.80",
            windows_build=26100,
            windows_version="24H2",
            is_windows_11=True,
            is_admin=True,
            features={"docker"},
            feature_labels={"docker": "Docker Desktop"},
            has_vrr_monitor=True,
        )
        assert ctx.to_dict() == {
            "cpu_vendor": "amd",
            "gpu_vendor": "nvidia",
            "gpu_vendors": ["nvidia", "intel"],
            "gpu_name": "X",
            "gpu_driver_version": "576.80",
            "windows_build": 26100,
            "windows_version": "24H2",
            "is_windows_11": True,
            "is_admin": True,
            "features": ["docker"],
            "feature_labels": {"docker": "Docker Desktop"},
            "has_vrr_monitor": True,
        }


class TestDeclaredGates:
    """`min_os_build` and `driver_gate` are typed gates checked here and nowhere else."""

    def test_an_unread_build_fails_every_floor(self) -> None:
        checker = ApplicabilityChecker(HardwareContext(windows_build=0))
        setting = _setting(min_os_build=22000)
        assert checker.is_applicable(setting) == (False, "Requires Windows build 22000+")

    def test_a_boolean_floor_is_not_a_gate(self) -> None:
        checker = ApplicabilityChecker(HardwareContext(windows_build=0))
        setting = _setting(min_os_build=True)
        assert checker.is_applicable(setting) == (True, "")

    def test_a_non_integer_floor_is_not_a_gate(self) -> None:
        checker = ApplicabilityChecker(HardwareContext(windows_build=0))
        setting = _setting(min_os_build="22000")
        assert checker.is_applicable(setting) == (True, "")

    def test_a_driver_gate_without_a_gpu_is_refused(self) -> None:
        checker = ApplicabilityChecker(HardwareContext(gpu_vendor=None))
        setting = _setting(driver_gate=DriverGate(vendor="nvidia", min_version="576.80"))
        assert checker.is_applicable(setting) == (False, "Requires NVIDIA GPU")

    def test_a_driver_gate_for_another_vendor_is_refused(self) -> None:
        checker = ApplicabilityChecker(HardwareContext(gpu_vendor="amd"))
        setting = _setting(driver_gate=DriverGate(vendor="nvidia", min_version="576.80"))
        assert checker.is_applicable(setting) == (False, "Requires NVIDIA GPU")

    def test_an_unread_driver_version_is_unknown_not_old(self) -> None:
        checker = ApplicabilityChecker(
            HardwareContext(gpu_vendor="nvidia", gpu_driver_version=None)
        )
        setting = _setting(driver_gate=DriverGate(vendor="nvidia", min_version="576.80"))
        applicable, reason = checker.is_applicable(setting)
        assert applicable is False
        assert "could not be read" in reason
        assert "NVIDIA" in reason

    def test_a_driver_below_the_floor_is_refused_with_the_floor(self) -> None:
        checker = ApplicabilityChecker(
            HardwareContext(gpu_vendor="nvidia", gpu_driver_version="570.00")
        )
        setting = _setting(driver_gate=DriverGate(vendor="nvidia", min_version="576.80"))
        assert checker.is_applicable(setting) == (False, "Requires NVIDIA driver 576.80+")

    def test_a_driver_above_the_ceiling_is_refused_with_the_ceiling(self) -> None:
        checker = ApplicabilityChecker(
            HardwareContext(gpu_vendor="nvidia", gpu_driver_version="576.80")
        )
        setting = _setting(driver_gate=DriverGate(vendor="nvidia", max_version="560.00"))
        assert checker.is_applicable(setting) == (
            False,
            "Requires NVIDIA driver 560.00 or earlier",
        )

    def test_a_driver_inside_the_range_is_offered(self) -> None:
        checker = ApplicabilityChecker(
            HardwareContext(gpu_vendor="nvidia", gpu_driver_version="576.80")
        )
        setting = _setting(
            driver_gate=DriverGate(vendor="nvidia", min_version="550.00", max_version="600.00")
        )
        assert checker.is_applicable(setting) == (True, "")

    def test_the_context_vendor_case_does_not_decide_the_gate(self) -> None:
        checker = ApplicabilityChecker(
            HardwareContext(gpu_vendor="NVIDIA", gpu_driver_version="576.80")
        )
        setting = _setting(driver_gate=DriverGate(vendor="nvidia", min_version="550.00"))
        assert checker.is_applicable(setting) == (True, "")

    def test_a_declared_gate_is_read_before_the_conditions(self) -> None:
        checker = ApplicabilityChecker(HardwareContext(windows_build=22631, is_admin=False))
        setting = _setting({"requires_admin": True}, min_os_build=99999)
        assert checker.is_applicable(setting) == (False, "Requires Windows build 99999+")


class TestConditionReasons:
    """Every condition type answers with its own sentence, in the documented order."""

    def test_cpu_vendor_unknown_and_mismatch_name_the_vendor(self) -> None:
        setting = _setting({"cpu_vendor": "Intel"})
        assert ApplicabilityChecker(HardwareContext(cpu_vendor=None)).is_applicable(setting) == (
            False,
            "Requires INTEL CPU",
        )
        assert ApplicabilityChecker(HardwareContext(cpu_vendor="amd")).is_applicable(setting) == (
            False,
            "Requires INTEL CPU",
        )
        assert ApplicabilityChecker(HardwareContext(cpu_vendor="INTEL")).is_applicable(setting) == (
            True,
            "",
        )

    def test_gpu_vendor_unknown_and_mismatch_name_the_vendor(self) -> None:
        setting = _setting({"gpu_vendor": "nvidia"})
        assert ApplicabilityChecker(HardwareContext(gpu_vendor=None)).is_applicable(setting) == (
            False,
            "Requires NVIDIA GPU",
        )
        assert ApplicabilityChecker(HardwareContext(gpu_vendor="amd")).is_applicable(setting) == (
            False,
            "Requires NVIDIA GPU",
        )
        assert ApplicabilityChecker(HardwareContext(gpu_vendor="NVIDIA")).is_applicable(
            setting
        ) == (
            True,
            "",
        )

    def test_gpu_vendors_accepts_any_listed_vendor(self) -> None:
        setting = _setting({"gpu_vendors": ["nvidia", "amd"]})
        expected = "Requires GPU: NVIDIA, AMD"
        assert ApplicabilityChecker(HardwareContext(gpu_vendor=None)).is_applicable(setting) == (
            False,
            expected,
        )
        assert ApplicabilityChecker(HardwareContext(gpu_vendor="intel")).is_applicable(setting) == (
            False,
            expected,
        )
        assert ApplicabilityChecker(HardwareContext(gpu_vendor="AMD")).is_applicable(setting) == (
            True,
            "",
        )

    def test_windows_11_condition_only_rejects_a_known_non_11(self) -> None:
        setting = _setting({"is_windows_11": True})
        assert ApplicabilityChecker(HardwareContext(is_windows_11=False)).is_applicable(
            setting
        ) == (
            False,
            "Requires Windows 11",
        )
        assert ApplicabilityChecker(HardwareContext(is_windows_11=True)).is_applicable(setting) == (
            True,
            "",
        )
        assert ApplicabilityChecker(HardwareContext()).is_applicable(
            _setting({"is_windows_11": False})
        ) == (True, "")

    def test_admin_condition_answers_only_when_required(self) -> None:
        setting = _setting({"requires_admin": True})
        assert ApplicabilityChecker(HardwareContext(is_admin=False)).is_applicable(setting) == (
            False,
            "Requires administrator privileges",
        )
        assert ApplicabilityChecker(HardwareContext(is_admin=True)).is_applicable(setting) == (
            True,
            "",
        )
        assert ApplicabilityChecker(HardwareContext(is_admin=False)).is_applicable(
            _setting({"requires_admin": False})
        ) == (True, "")

    def test_a_vrr_panel_rules_out_a_setting_that_would_stop_it(self) -> None:
        setting = _setting({"requires_vrr": False})
        reason = "Not offered with a G-Sync/FreeSync/VRR monitor: it can stop VRR engaging"
        assert ApplicabilityChecker(HardwareContext(has_vrr_monitor=True)).is_applicable(
            setting
        ) == (False, reason)
        assert ApplicabilityChecker(HardwareContext(has_vrr_monitor=False)).is_applicable(
            setting
        ) == (True, "")
        assert ApplicabilityChecker(HardwareContext(has_vrr_monitor=None)).is_applicable(
            setting
        ) == (True, "")

    def test_a_feature_condition_names_the_missing_feature(self) -> None:
        setting = _setting({"feature": "docker"})
        assert ApplicabilityChecker(HardwareContext(features={"docker"})).is_applicable(
            setting
        ) == (True, "")
        assert ApplicabilityChecker(HardwareContext(features=set())).is_applicable(setting) == (
            False,
            "Requires docker feature",
        )

    def test_a_present_feature_is_named_in_its_own_words(self) -> None:
        setting = _setting({"feature_absent": "virtualization_in_use"})
        labelled = HardwareContext(
            features={"virtualization_in_use"},
            feature_labels={"virtualization_in_use": "Docker Desktop and WSL (2 distributions)"},
        )
        assert ApplicabilityChecker(labelled).is_applicable(setting) == (
            False,
            "Not recommended: would break Docker Desktop and WSL (2 distributions)",
        )
        unlabelled = HardwareContext(features={"virtualization_in_use"})
        assert ApplicabilityChecker(unlabelled).is_applicable(setting) == (
            False,
            "Not recommended: would break virtualization_in_use",
        )
        assert ApplicabilityChecker(HardwareContext(features=set())).is_applicable(setting) == (
            True,
            "",
        )

    def test_features_any_needs_one_and_features_all_needs_every_one(self) -> None:
        any_setting = _setting({"features_any": ["docker"]})
        assert ApplicabilityChecker(HardwareContext(features=set())).is_applicable(any_setting) == (
            False,
            "Requires one of: docker",
        )
        assert ApplicabilityChecker(HardwareContext(features={"docker"})).is_applicable(
            any_setting
        ) == (True, "")

        all_setting = _setting({"features_all": ["hyper_v"]})
        assert ApplicabilityChecker(HardwareContext(features=set())).is_applicable(all_setting) == (
            False,
            "Requires: hyper_v",
        )
        assert ApplicabilityChecker(HardwareContext(features={"hyper_v"})).is_applicable(
            all_setting
        ) == (True, "")

    def test_the_first_failing_condition_supplies_the_reason(self) -> None:
        checker = ApplicabilityChecker(HardwareContext(cpu_vendor="intel", gpu_vendor="nvidia"))
        setting = _setting({"cpu_vendor": "amd", "gpu_vendor": "amd"})
        assert checker.is_applicable(setting) == (False, "Requires AMD CPU")


class TestProtectedWrite:
    """A UCPD-guarded key is off the table before any other condition is read."""

    @staticmethod
    def _guarded_setting() -> MagicMock:
        setting = _setting()
        setting.apply_type = DetectType.REGISTRY
        setting.apply_args = {
            "hive": "HKLM",
            "path": r"software\policies\microsoft\dsh",
            "name": "",
        }
        return setting

    def test_a_guarded_key_is_refused_while_the_guard_is_up(self) -> None:
        checker = ApplicabilityChecker(HardwareContext(ucpd_guard_up=True))
        applicable, reason = checker.is_applicable(self._guarded_setting())
        assert applicable is False
        assert "User Choice Protection Driver" in reason
        assert "HKLM" in reason

    def test_the_same_key_is_offered_once_the_guard_is_down(self) -> None:
        checker = ApplicabilityChecker(HardwareContext(ucpd_guard_up=False))
        assert checker.is_applicable(self._guarded_setting()) == (True, "")

    def test_the_guard_is_read_before_the_conditions(self) -> None:
        setting = self._guarded_setting()
        setting.applicable_conditions = {"requires_admin": True}
        checker = ApplicabilityChecker(HardwareContext(ucpd_guard_up=True, is_admin=False))
        applicable, reason = checker.is_applicable(setting)
        assert applicable is False
        assert "User Choice Protection Driver" in reason


class TestValuesEqualEdgeCases:
    """The coercion corners C6's verify path depends on."""

    def test_lone_carriage_returns_are_normalised(self) -> None:
        assert values_equal("a\rb", "a\nb") is True

    def test_float_strings_coerce_like_numbers(self) -> None:
        assert values_equal("1.5", 1.5) is True
        assert values_equal("1.5", 1) is False

    def test_a_boolean_compares_as_its_integer_value_across_types(self) -> None:
        # bool is an int subclass; only bool-vs-bool is decided by the bool branch.
        assert values_equal(True, 1) is True
        assert values_equal(False, 0) is True

    def test_unrelated_types_are_not_equal(self) -> None:
        assert values_equal("1", [1]) is False
        assert values_equal([1], {"a": 1}) is False

    def test_whitespace_only_equals_an_empty_string(self) -> None:
        assert values_equal("   ", "") is True
