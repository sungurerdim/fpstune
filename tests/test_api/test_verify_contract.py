"""Contract tests for the post-apply verification path.

These guard the rule that a setting is exempt from verification only when it is
genuinely advisory (``is_readonly``). Testing ``apply_command`` instead — as the
code did before — exempted every registry/powercfg/nvprofile setting, because
those executors carry their target in ``apply_args`` and leave the command empty.
"""

from __future__ import annotations

from fpstune.api.routes.settings import _SLOW_RESET_TOLERANCES, _verify_setting_applied
from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)


def _registry_setting(**overrides) -> SettingExecutor:
    """Build a registry-backed setting — apply_command is empty by design."""
    kwargs = {
        "id": "test:registry_backed",
        "category": SettingCategory.CORE,
        "display_name": "Registry Backed",
        "description": "Registry setting whose target lives in apply_args.",
        "value_type": SettingValueType.CHOICE,
        "choices": ("enabled", "disabled"),
        "default_value": "enabled",
        "recommended_value": "disabled",
        "detect_type": DetectType.REGISTRY,
        "detect_command": "",
        "detect_args": {"path": "Control Panel\\Desktop", "name": "SmoothScroll"},
        "apply_type": DetectType.REGISTRY,
        "apply_command": "",
        "apply_args": {"path": "Control Panel\\Desktop", "name": "SmoothScroll"},
    }
    kwargs.update(overrides)
    return SettingExecutor(**kwargs)


class TestVerificationIsNotSkippedForRegistrySettings:
    """An empty apply_command must not exempt a setting from verification."""

    def test_mismatch_on_registry_setting_fails_verification(self):
        """Guards the 108-setting silent-pass bug: apply_command="" was treated
        as 'advisory' and returned success for an unapplied setting."""
        setting = _registry_setting()

        ok, error, verified = _verify_setting_applied(setting, "disabled", "enabled")

        assert ok is False
        assert error is not None
        assert "disabled" in error and "enabled" in error
        assert verified is False

    def test_match_on_registry_setting_passes_verification(self):
        setting = _registry_setting()

        ok, error, verified = _verify_setting_applied(setting, "disabled", "disabled")

        assert ok is True
        assert error is None
        assert verified is True

    def test_undetectable_value_fails_verification(self):
        """A None read-back means we cannot prove the write landed."""
        setting = _registry_setting()

        ok, error, verified = _verify_setting_applied(setting, "disabled", None)

        assert ok is False
        assert error is not None
        assert verified is False


class TestVerificationExemptions:
    """Only genuinely non-writable settings may skip verification."""

    def test_readonly_setting_is_exempt(self):
        """Advisory settings (BIOS, fan curves) have nothing to read back."""
        setting = _registry_setting(id="test:advisory", is_readonly=True)

        ok, error, verified = _verify_setting_applied(setting, "disabled", "enabled")

        assert ok is True
        assert error is None
        # A skipped check must not be reported as a passed one.
        assert verified is None

    def test_action_setting_is_exempt(self):
        """One-shot actions (TRIM, cleanup) leave no persistent value."""
        setting = _registry_setting(id="test:action", is_action=True)

        ok, error, verified = _verify_setting_applied(setting, True, False)

        assert ok is True
        assert error is None
        assert verified is None

    def test_reboot_setting_is_still_verified(self):
        """requires_reboot means the *effect* is deferred, not that the value
        is unreadable — a failed write must not report success."""
        setting = _registry_setting(id="test:reboot", requires_reboot=True)

        ok, error, verified = _verify_setting_applied(setting, "disabled", "enabled")

        assert ok is False
        assert error is not None
        assert verified is False


class TestNvidiaSettingsAreReportedUnverified:
    """NVIDIA detection returns fpstune's own JSON cache, which apply just
    wrote. A match between them proves nothing about the driver, so the result
    must be reported as unverified rather than as a passed check."""

    def _nv_setting(self) -> SettingExecutor:
        return SettingExecutor(
            id="gpu-nvidia:low_latency",
            category=SettingCategory.GPU,
            display_name="Low Latency Mode",
            description="NVIDIA Reflex / Ultra Low Latency mode.",
            value_type=SettingValueType.CHOICE,
            choices=("off", "on", "ultra"),
            default_value="off",
            recommended_value="on",
            detect_type=DetectType.NVPROFILE,
            detect_command="",
            detect_args={"setting": "low_latency"},
            apply_type=DetectType.NVPROFILE,
            apply_command="",
            apply_args={"setting": "low_latency"},
        )

    def test_matching_cache_value_is_not_claimed_as_verified(self):
        ok, error, verified = _verify_setting_applied(self._nv_setting(), "on", "on")

        assert ok is True
        assert error is None
        # The apply is not failed — but it was never actually checked.
        assert verified is None

    def test_mismatch_is_also_reported_unverified(self):
        """Even a mismatch here says nothing about the driver state."""
        ok, error, verified = _verify_setting_applied(self._nv_setting(), "on", "off")

        assert ok is True
        assert verified is None


class TestDeprecatedIdCompatLayerIsGone:
    """The one-entry ``_DEPRECATED_ID_MAP`` and its ``_resolve_setting_id``
    layer were removed: an unpublished product with no external consumers gets
    the breaking change, not a shim. An id the registry does not know must now
    answer 404 like any other unknown id, rather than being quietly rewritten
    into a different setting's."""

    def test_the_split_compound_id_is_now_unknown(self, test_client):
        response = test_client.post("/api/settings/system:network_afd_buffers/verify")

        assert response.status_code == 404

    def test_the_replacement_id_still_resolves(self, test_client):
        """The removal must take the alias, not the setting it pointed at."""
        response = test_client.post("/api/settings/system:network_afd_receive_window/verify")

        assert response.status_code == 200
        assert response.json()["setting_id"] == "system:network_afd_receive_window"


class TestSlowResetTolerancesAreWiredToRealSettings:
    """``_SLOW_RESET_TOLERANCES`` names settings by id from outside the registry.

    The rule used to be an ``if setting.id == "network:dns_security"`` branch in
    the middle of a verifier that runs for every setting, so renaming the
    setting would have left the branch matching nothing and the reset reporting
    a false verification failure — with no test red. The table can drift the same
    way; this is the check that stops it.
    """

    def _registry_ids(self) -> set[str]:
        from fpstune.settings import SettingsRegistry

        return {s.id for s in SettingsRegistry().get_all()}

    def test_every_tolerance_names_a_registered_setting(self):
        unknown = sorted(set(_SLOW_RESET_TOLERANCES) - self._registry_ids())

        assert not unknown, (
            f"_SLOW_RESET_TOLERANCES names settings that are not registered: {unknown}. "
            "A renamed setting silently loses its reset tolerance and starts "
            "reporting a successful reset as a verification failure."
        )


class TestDnsResetTolerance:
    """DNS reset lands after DHCP propagation, later than the read-back."""

    def _dns_setting(self) -> SettingExecutor:
        return SettingExecutor(
            id="network:dns_security",
            category=SettingCategory.NETWORK,
            display_name="DNS Provider",
            description="Which resolver the adapter uses. A filtering resolver blocks "
            "malware and ad domains before the connection is made.",
            value_type=SettingValueType.CHOICE,
            choices=("default", "cloudflare", "cloudflare_security", "cloudflare_family"),
            default_value="default",
            recommended_value="cloudflare_security",
            detect_type=DetectType.POWERSHELL,
            detect_command="Get-DnsClientServerAddress",
            detect_args={},
            apply_type=DetectType.POWERSHELL,
            apply_command="Set-DnsClientServerAddress",
            apply_args={},
        )

    def test_a_non_cloudflare_reading_counts_the_reset_as_landed(self):
        ok, error, verified = _verify_setting_applied(self._dns_setting(), "default", "192.168.1.1")

        assert ok is True
        assert error is None
        assert verified is True

    def test_a_still_cloudflare_reading_fails_the_reset(self):
        ok, error, verified = _verify_setting_applied(self._dns_setting(), "default", "cloudflare")

        assert ok is False
        assert error is not None and "adapter restart" in error
        assert verified is False

    def test_the_tolerance_applies_only_to_the_reset_direction(self):
        """Applying a provider is verified strictly — the tolerance exists for
        the DHCP hand-back, not as a blanket exemption for this setting."""
        ok, error, verified = _verify_setting_applied(
            self._dns_setting(), "cloudflare_security", "cloudflare"
        )

        assert ok is False
        assert verified is False
