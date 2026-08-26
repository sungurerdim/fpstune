"""Tests for settings applicability checks and values_equal comparison."""

from __future__ import annotations

import pytest

from fpstune.settings.applicability import (
    ANTICHEAT_RISKY_SETTINGS,
    ANTICHEAT_WARNINGS,
    ApplicabilityChecker,
    HardwareContext,
    values_equal,
)


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
        assert ctx.has_vrr_monitor is False

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
            has_anticheat_games=False,
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

    def test_min_windows_build(self, nvidia_intel_context: HardwareContext) -> None:
        """Setting with min_windows_build should check build number."""
        checker = ApplicabilityChecker(nvidia_intel_context)  # build 22631
        setting = self._make_setting({"min_windows_build": 22000})
        is_applicable, _ = checker.is_applicable(setting)
        assert is_applicable is True

    def test_min_windows_build_too_low(self, nvidia_intel_context: HardwareContext) -> None:
        """Setting with min_windows_build above current should reject."""
        checker = ApplicabilityChecker(nvidia_intel_context)  # build 22631
        setting = self._make_setting({"min_windows_build": 99999})
        is_applicable, _ = checker.is_applicable(setting)
        assert is_applicable is False

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

    def test_get_applicable_settings_filters(self, nvidia_intel_context: HardwareContext) -> None:
        """get_applicable_settings() should return only matching settings."""
        checker = ApplicabilityChecker(nvidia_intel_context)
        nvidia_setting = self._make_setting({"gpu_vendor": "nvidia"})
        amd_setting = self._make_setting({"gpu_vendor": "amd"})
        universal_setting = self._make_setting({})

        result = checker.get_applicable_settings([nvidia_setting, amd_setting, universal_setting])
        assert len(result) == 2
        assert nvidia_setting in result
        assert universal_setting in result
        assert amd_setting not in result


class TestAnticheatTableIsNotStale:
    """The anti-cheat table names setting ids, and nothing used to check them.

    Three of the four ids it shipped with named settings this product no longer
    has (``system:kernel_debugging``, ``system:test_signing``,
    ``system:driver_verifier``). Each was removed without its warning, and
    nothing anywhere went red — ``check_anticheat_compatibility`` simply stopped
    matching and returned "safe". A dropped anti-cheat warning is not a cosmetic
    regression: the user it fails is the one who applies the risky value, is
    never told, and gets banned.

    ``applicability.py`` cannot make this an import-time check the way
    ``powershell_actions._wire_mutex_groups`` does — executors import it while
    the registry is still being built, so reaching for the registry there is a
    cycle. This is where the check lives instead.
    """

    @staticmethod
    def _registry_ids() -> set[str]:
        from fpstune.settings.registry import SettingsRegistry

        return {s.id for s in SettingsRegistry().get_all()}

    def test_every_warned_id_is_a_setting_that_exists(self) -> None:
        unknown = sorted(set(ANTICHEAT_WARNINGS) - self._registry_ids())
        assert not unknown, (
            f"ANTICHEAT_WARNINGS names settings that are not registered: {unknown}. "
            "Rename the entry together with the setting, or its anti-cheat warning "
            "silently stops firing."
        )

    def test_the_risky_set_cannot_drift_from_the_warnings(self) -> None:
        # These were two hand-written lists of the same ids. An id in one and not
        # the other produced either a warning that never fired or a generic
        # "May conflict with anti-cheat software" with none of the specifics.
        assert frozenset(ANTICHEAT_WARNINGS) == ANTICHEAT_RISKY_SETTINGS

    def test_a_risky_setting_still_warns(self) -> None:
        from fpstune.settings.registry import SettingsRegistry

        setting = SettingsRegistry().get("gpu-nvidia:low_latency")
        assert setting is not None
        checker = ApplicabilityChecker(HardwareContext(has_anticheat_games=True))

        is_safe, warning = checker.check_anticheat_compatibility(setting, "ultra")
        assert is_safe is False
        assert "anti-cheat" in warning.lower()

        # Only "ultra" is the risky value; fpstune's own recommendation is "on".
        assert checker.check_anticheat_compatibility(setting, "on") == (True, "")
