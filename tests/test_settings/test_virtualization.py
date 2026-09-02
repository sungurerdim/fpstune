"""The virtualization consumers that decide whether disabling the platform is safe.

This file exists because of a shipped C9 bug. ``hardware_context`` gated both
platform-disabling settings on one hardcoded path::

    C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe

Docker Desktop now installs per-user by default, so on a machine running Docker
29.7.2 the probe answered "no Docker": ``system:hyper_v`` and
``system:vm_platform`` were recommended to the user whose containers run on that
platform, and ``cleanup:docker_prune`` was hidden from the same user. Both
directions of the same wrong answer.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from fpstune.settings.applicability import ApplicabilityChecker, HardwareContext
from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.virtualization import (
    VIRTUALIZATION_IN_USE,
    VirtualizationConsumer,
    detect_virtualization_consumers,
    virtualization_features,
)


def _setting(conditions: dict[str, Any]) -> SettingExecutor:
    """A minimal setting carrying just the applicability conditions under test."""
    return SettingExecutor(
        id="system:probe",
        category=SettingCategory.SYSTEM,
        display_name="Probe",
        short_name="Probe",
        description="Stands in for a real setting. Only the conditions matter.",
        value_type=SettingValueType.CHOICE,
        choices=("enabled", "disabled"),
        default_value="disabled",
        recommended_value="disabled",
        current_impact="Enabled: stands in",
        recommended_impact="Disabled: stands in",
        effect="Stands in for a real setting",
        impact_scores={"fps_cpu_bound": "+0-2%"},
        applicable_conditions=conditions,
        detect_type=DetectType.POWERSHELL,
        detect_command="'disabled'",
        apply_type=DetectType.POWERSHELL,
        apply_command="noop",
    )


class TestConsumerDetection:
    """What the probes find, and what they refuse to guess."""

    def test_per_user_docker_install_is_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The exact install shape that defeated the hardcoded path.

        Docker Desktop's per-user install writes its uninstall entry under HKCU
        and its files under %LOCALAPPDATA%, so nothing lands in Program Files.
        """
        from fpstune.settings import virtualization

        def fake_key_exists(root: str, path: str) -> bool:
            return root == "HKCU" and path.endswith("Docker Desktop")

        monkeypatch.setattr(virtualization, "_registry_key_exists", fake_key_exists)

        found = virtualization._docker_desktop()
        assert found is not None
        assert found.key == "docker"
        assert "per-user" in found.evidence

    def test_no_docker_anywhere_reports_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Absent is a real answer, not a failure — it is what makes the setting safe."""
        import shutil

        from fpstune.settings import virtualization

        monkeypatch.setattr(virtualization, "_registry_key_exists", lambda _root, _path: False)
        monkeypatch.setattr(shutil, "which", lambda _name: None)

        assert virtualization._docker_desktop() is None

    def test_docker_on_path_without_uninstall_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An engine installed without Docker Desktop still consumes the platform."""
        import shutil

        from fpstune.settings import virtualization

        monkeypatch.setattr(virtualization, "_registry_key_exists", lambda _root, _path: False)
        monkeypatch.setattr(shutil, "which", lambda _name: r"C:\tools\docker.exe")

        found = virtualization._docker_desktop()
        assert found is not None
        assert found.key == "docker"

    @pytest.mark.skipif(sys.platform != "win32", reason="registry probe is Windows-only")
    def test_wsl_count_is_reported_not_just_presence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two distributions read differently from one, so the label carries the count."""
        import winreg

        from fpstune.settings import virtualization

        class _FakeKey:
            def __enter__(self) -> _FakeKey:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        monkeypatch.setattr(winreg, "OpenKey", lambda *_a, **_k: _FakeKey())
        monkeypatch.setattr(winreg, "QueryInfoKey", lambda _key: (2, 0, 0))

        found = virtualization._wsl_distributions()
        assert found is not None
        assert found.key == "wsl"
        assert "2 distributions" in found.label

    @pytest.mark.skipif(sys.platform != "win32", reason="registry probe is Windows-only")
    def test_wsl_with_zero_distributions_is_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The key survives uninstalling the last distribution; an empty key is not a consumer."""
        import winreg

        from fpstune.settings import virtualization

        class _FakeKey:
            def __enter__(self) -> _FakeKey:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        monkeypatch.setattr(winreg, "OpenKey", lambda *_a, **_k: _FakeKey())
        monkeypatch.setattr(winreg, "QueryInfoKey", lambda _key: (0, 0, 0))

        assert virtualization._wsl_distributions() is None

    def test_hyper_v_feature_without_a_vm_is_not_a_consumer(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Carrying Hyper-V is not using it — only a configured VM is something to lose."""
        from fpstune.settings import virtualization

        vm_dir = tmp_path / "Microsoft" / "Windows" / "Hyper-V" / "Virtual Machines"
        vm_dir.mkdir(parents=True)
        monkeypatch.setenv("PROGRAMDATA", str(tmp_path))

        assert virtualization._hyper_v_machines() is None

        (vm_dir / "9C2B1F0A-0000-0000-0000-000000000001.vmcx").write_bytes(b"")
        found = virtualization._hyper_v_machines()
        assert found is not None
        assert found.key == "hyper_v_vm"
        assert "1 virtual machine" in found.label

    def test_a_failing_probe_never_answers_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A probe that raises is skipped and logged — never counted as "nothing here".

        The distinction is the whole safety property: "we could not tell" must
        not become "safe to disable".
        """
        from fpstune.settings import virtualization

        def boom() -> VirtualizationConsumer | None:
            raise OSError("registry unavailable")

        def fine() -> VirtualizationConsumer | None:
            return VirtualizationConsumer(key="wsl", label="WSL (1 distribution)", evidence="test")

        monkeypatch.setattr(virtualization, "_PROBES", (boom, fine))

        consumers = detect_virtualization_consumers()
        assert [c.key for c in consumers] == ["wsl"]


class TestFeatureRollup:
    """The flag the settings actually gate on."""

    def test_every_consumer_contributes_its_own_key_and_the_rollup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`cleanup:docker_prune` needs `docker` specifically; the VM settings need the rollup."""
        from fpstune.settings import virtualization

        monkeypatch.setattr(
            virtualization,
            "detect_virtualization_consumers",
            lambda: [
                VirtualizationConsumer(key="docker", label="Docker Desktop", evidence="test"),
                VirtualizationConsumer(key="wsl", label="WSL (1 distribution)", evidence="test"),
            ],
        )

        flags, _ = virtualization.virtualization_features()
        assert flags == {"docker", "wsl", VIRTUALIZATION_IN_USE}

    def test_no_consumers_means_no_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty machine must not carry the rollup, or nothing is ever recommendable."""
        from fpstune.settings import virtualization

        monkeypatch.setattr(virtualization, "detect_virtualization_consumers", lambda: [])
        assert virtualization.virtualization_features() == (set(), {})

    def test_the_rollup_label_names_every_consumer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The label is what the user reads instead of an internal token."""
        from fpstune.settings import virtualization

        monkeypatch.setattr(
            virtualization,
            "detect_virtualization_consumers",
            lambda: [
                VirtualizationConsumer(key="docker", label="Docker Desktop", evidence="test"),
                VirtualizationConsumer(key="wsl", label="WSL (1 distribution)", evidence="test"),
            ],
        )

        _, labels = virtualization.virtualization_features()
        assert labels[VIRTUALIZATION_IN_USE] == "Docker Desktop and WSL (1 distribution)"
        assert labels["docker"] == "Docker Desktop"

    def test_a_single_consumer_reads_as_itself(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No dangling "and" when there is only one thing to break."""
        from fpstune.settings import virtualization

        monkeypatch.setattr(
            virtualization,
            "detect_virtualization_consumers",
            lambda: [
                VirtualizationConsumer(key="wsl", label="WSL (2 distributions)", evidence="test")
            ],
        )

        _, labels = virtualization.virtualization_features()
        assert labels[VIRTUALIZATION_IN_USE] == "WSL (2 distributions)"


class TestPlatformSettingsAreGated:
    """The two settings whose recommendation was wrong on a Docker machine."""

    @pytest.mark.parametrize("consumer", ["docker", "wsl", "hyper_v_vm", "wsa"])
    def test_any_consumer_hides_the_disable_recommendation(self, consumer: str) -> None:
        """WSL alone must hide it too — the old gate only ever knew about Docker."""
        ctx = HardwareContext(
            is_admin=True,
            windows_build=26200,
            is_windows_11=True,
            features={consumer, VIRTUALIZATION_IN_USE},
        )
        setting = _setting({"requires_admin": True, "feature_absent": VIRTUALIZATION_IN_USE})

        applicable, reason = ApplicabilityChecker(ctx).is_applicable(setting)
        assert applicable is False
        assert reason

    def test_a_machine_with_nothing_virtual_still_gets_the_setting(self) -> None:
        """The gate must not hide the setting from everyone — it is a real tweak."""
        ctx = HardwareContext(
            is_admin=True,
            windows_build=26200,
            is_windows_11=True,
            features=set(),
        )
        setting = _setting({"requires_admin": True, "feature_absent": VIRTUALIZATION_IN_USE})

        applicable, _ = ApplicabilityChecker(ctx).is_applicable(setting)
        assert applicable is True

    def test_the_reason_names_what_would_break(self) -> None:
        """The user's question is "am I losing something I use?".

        The reason used to read "Not recommended: virtualization_in_use is
        installed (would break it)" — a token that names nothing on the machine,
        so it could not answer that question either way.
        """
        ctx = HardwareContext(
            is_admin=True,
            windows_build=26200,
            is_windows_11=True,
            features={"docker", "wsl", VIRTUALIZATION_IN_USE},
            feature_labels={
                "docker": "Docker Desktop",
                "wsl": "WSL (1 distribution)",
                VIRTUALIZATION_IN_USE: "Docker Desktop and WSL (1 distribution)",
            },
        )
        setting = _setting({"requires_admin": True, "feature_absent": VIRTUALIZATION_IN_USE})

        _, reason = ApplicabilityChecker(ctx).is_applicable(setting)

        assert reason == "Not recommended: would break Docker Desktop and WSL (1 distribution)"
        assert VIRTUALIZATION_IN_USE not in reason

    def test_an_unlabelled_feature_still_produces_a_reason(self) -> None:
        """Every other feature has no label, and must not lose its reason for it."""
        ctx = HardwareContext(is_admin=True, features={"xbox_game_bar"})
        setting = _setting({"feature_absent": "xbox_game_bar"})

        applicable, reason = ApplicabilityChecker(ctx).is_applicable(setting)

        assert applicable is False
        assert "xbox_game_bar" in reason

    def test_registered_settings_use_the_rollup_not_docker_alone(self) -> None:
        """Pins the fix in place: neither setting may go back to gating on `docker`.

        Gating on Docker alone is what made a WSL-only machine — no Docker at
        all — a machine fpstune told to remove WSL2's platform out from under it.
        """
        from fpstune.settings.definitions.system import SYSTEM_HYPER_V, SYSTEM_VM_PLATFORM

        for setting in (SYSTEM_HYPER_V, SYSTEM_VM_PLATFORM):
            assert setting.applicable_conditions["feature_absent"] == VIRTUALIZATION_IN_USE


class TestRealMachine:
    """One check against whatever this machine actually is."""

    @pytest.mark.skipif(sys.platform != "win32", reason="probes are Windows-only")
    def test_probes_return_well_formed_consumers(self) -> None:
        """Whatever is or is not installed, every answer is usable by the UI."""
        for consumer in detect_virtualization_consumers():
            assert consumer.key
            assert consumer.label
            # The evidence is what a user reads when asking "how do you know?" —
            # an empty one makes the confirmation unanswerable.
            assert consumer.evidence

        features, labels = virtualization_features()
        if features:
            assert VIRTUALIZATION_IN_USE in features
            # A flag with no label puts an internal token in front of the user.
            assert labels.get(VIRTUALIZATION_IN_USE)
