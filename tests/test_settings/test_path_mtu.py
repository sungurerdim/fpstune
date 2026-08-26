"""The MTU target must be measured, and absent when it cannot be.

An MTU tweak is the sharpest example of the product's first rule. On this dev
machine the line is PPPoE: 1500-byte frames are rejected, 1492 pass. A tool that
"restored 1500" would cause the fragmentation it claims to fix, and a tool that
hardcoded 1492 would shave 8 bytes off every frame on the majority of connections
that really do carry 1500. Both are the same defect — a constant standing in for a
measurement.

The failure mode these tests exist for is subtler than a wrong constant: a probe
that talks itself downwards. Only an ICMP "packet too big" proves a size is too
large. A timeout proves nothing — a dropped probe, a rate limiter and a firewall
that eats ICMP are indistinguishable — so a probe that treats silence as "too big"
converges on its floor and caps a healthy line. Silence has to abort the search.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest

from fpstune.settings.discovery.network import register_path_mtu_setting
from fpstune.settings.discovery.probes import HardwareProbes
from fpstune.settings.registry import SettingsRegistry
from fpstune.utils import path_mtu


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    path_mtu.reset_cache()
    yield
    path_mtu.reset_cache()


def _fake_runner(answers: dict[int, str], calls: list[int] | None = None):
    """Stand in for PowerShell by evaluating the probe script's decisions in Python.

    The script itself is exercised for real against the host in
    ``test_the_shipped_probe_agrees_with_the_host`` below; this fake covers the
    paths a real network will not reproduce on demand — a filtered path, a
    mid-search timeout, a nonsense answer.
    """

    def run(script: str, **_kwargs: object) -> tuple[bool, str]:  # noqa: ARG001
        hi, lo = 1472, 1252
        top = answers.get(hi, "unknown")
        if calls is not None:
            calls.append(hi)
        if top == "ok":
            return True, f"mtu={hi + 28}"
        if top != "toobig":
            return True, "unknown"
        if calls is not None:
            calls.append(lo)
        if answers.get(lo, "unknown") != "ok":
            return True, "unknown"
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if calls is not None:
                calls.append(mid)
            verdict = answers.get(mid, "unknown")
            if verdict == "ok":
                lo = mid
            elif verdict == "toobig":
                hi = mid
            else:
                return True, "unknown"
        return True, f"mtu={lo + 28}"

    return run


def _answers_for(path_mtu_bytes: int) -> dict[int, str]:
    """Every payload size answers as a path of exactly `path_mtu_bytes` would."""
    limit = path_mtu_bytes - 28
    return {size: ("ok" if size <= limit else "toobig") for size in range(1252, 1473)}


def test_a_pppoe_path_is_measured_as_1492(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dev machine's real line, and the number this whole feature exists for."""
    monkeypatch.setattr("fpstune.utils.powershell.run_powershell", _fake_runner(_answers_for(1492)))
    assert path_mtu.probe_path_mtu() == 1492


def test_a_plain_ethernet_path_is_measured_as_1500(monkeypatch: pytest.MonkeyPatch) -> None:
    """The common case must not be dragged down by a probe that assumes trouble."""
    monkeypatch.setattr("fpstune.utils.powershell.run_powershell", _fake_runner(_answers_for(1500)))
    assert path_mtu.probe_path_mtu() == 1500


def test_a_full_size_frame_getting_through_ends_the_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One probe, not nine, when there is nothing to find."""
    calls: list[int] = []
    monkeypatch.setattr(
        "fpstune.utils.powershell.run_powershell", _fake_runner(_answers_for(1500), calls)
    )
    assert path_mtu.probe_path_mtu() == 1500
    assert calls == [1472]


def test_a_filtered_path_measures_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ICMP answers at all: the honest result is None, not a floor value.

    This is the case that decides whether the setting ships a guess. `None` means
    the MTU setting is not registered, so the user is offered nothing rather than
    a number nobody measured.
    """
    monkeypatch.setattr("fpstune.utils.powershell.run_powershell", _fake_runner({}))
    assert path_mtu.probe_path_mtu() is None


def test_silence_partway_through_aborts_instead_of_guessing_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timeout in the middle of the search must not be read as 'too big'.

    Reading it that way is how a probe walks itself down to the floor and caps a
    line that was fine — the exact harm the product goal's third clause names.
    """
    answers = _answers_for(1492)
    answers[1362] = "unknown"  # the first midpoint after the bounds are established
    monkeypatch.setattr("fpstune.utils.powershell.run_powershell", _fake_runner(answers))
    assert path_mtu.probe_path_mtu() is None


def test_a_result_outside_the_searched_range_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the script answers something the search cannot produce, it is not trusted."""
    monkeypatch.setattr(
        "fpstune.utils.powershell.run_powershell",
        lambda script, **_kwargs: (True, "mtu=9000"),  # noqa: ARG005
    )
    assert path_mtu.probe_path_mtu() is None


def test_a_failed_shell_measures_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "fpstune.utils.powershell.run_powershell",
        lambda script, **_kwargs: (False, "boom"),  # noqa: ARG005
    )
    assert path_mtu.probe_path_mtu() is None


def test_the_second_target_is_tried_when_the_first_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One unreachable resolver must not be enough to abandon the measurement."""
    seen: list[str] = []

    def run(script: str, **_kwargs: object) -> tuple[bool, str]:
        target = "1.1.1.1" if "1.1.1.1" in script else "8.8.8.8"
        seen.append(target)
        return (True, "unknown") if target == "1.1.1.1" else (True, "mtu=1492")

    monkeypatch.setattr("fpstune.utils.powershell.run_powershell", run)
    assert path_mtu.probe_path_mtu() == 1492
    assert seen == ["1.1.1.1", "8.8.8.8"]


def test_the_measurement_is_taken_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """A binary search per setting would put a network round trip inside every scan."""
    runs: list[int] = []

    def run(script: str, **_kwargs: object) -> tuple[bool, str]:  # noqa: ARG001
        runs.append(1)
        return True, "mtu=1492"

    monkeypatch.setattr("fpstune.utils.powershell.run_powershell", run)
    assert path_mtu.probe_path_mtu() == 1492
    assert path_mtu.probe_path_mtu() == 1492
    assert len(runs) == 1


def test_an_unmeasurable_path_is_also_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Otherwise every scan re-pays for the probe that already failed."""
    runs: list[int] = []

    def run(script: str, **_kwargs: object) -> tuple[bool, str]:  # noqa: ARG001
        runs.append(1)
        return True, "unknown"

    monkeypatch.setattr("fpstune.utils.powershell.run_powershell", run)
    assert path_mtu.probe_path_mtu() is None
    assert path_mtu.probe_path_mtu() is None
    assert len(runs) == 2  # one per target, then cached


ADAPTERS = [(17, "Ethernet", "802.3"), (4, "Wi-Fi", "Native 802.11")]


def _registry_with(
    monkeypatch: pytest.MonkeyPatch, *, route: int | None, measured: int | None
) -> tuple[SettingsRegistry, int]:
    # discover_dynamic=False, or the constructor registers this host's real adapters
    # first — and then the assertion "nothing was registered" reads the real machine
    # instead of the described one, which is a test passing for the wrong reason.
    registry = SettingsRegistry(discover_dynamic=False)
    monkeypatch.setattr(
        HardwareProbes,
        "default_route_interface_index",
        lambda self: route,  # noqa: ARG005
    )
    monkeypatch.setattr("fpstune.utils.path_mtu.probe_path_mtu", lambda: measured)
    return registry, register_path_mtu_setting(registry, registry._probes, ADAPTERS)


def test_the_setting_lands_on_the_adapter_the_probe_travelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measurement describes the default route, so it is offered there only.

    Registering the same number on the Wi-Fi adapter would claim a measurement that
    was never taken on that path.
    """
    registry, count = _registry_with(monkeypatch, route=17, measured=1492)
    assert count == 1
    setting = registry.get("network:17:mtu")
    assert setting is not None
    assert setting.recommended_value == 1492
    assert setting.default_value == 1500  # so reset means the Windows default
    assert registry.get("network:4:mtu") is None


def test_nothing_is_registered_when_the_probe_could_not_conclude(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No measurement, no setting — rather than a setting carrying a guess."""
    registry, count = _registry_with(monkeypatch, route=17, measured=None)
    assert count == 0
    assert registry.get("network:17:mtu") is None


def test_nothing_is_registered_without_a_default_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, count = _registry_with(monkeypatch, route=None, measured=1492)
    assert count == 0


def test_a_route_on_a_vpn_or_virtual_switch_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Index 42 is not one of the physical adapters, so its MTU is not fpstune's."""
    registry, count = _registry_with(monkeypatch, route=42, measured=1492)
    assert count == 0
    assert registry.get("network:42:mtu") is None


@pytest.mark.skipif(sys.platform != "win32", reason="Runs the shipped probe script")
def test_the_shipped_probe_agrees_with_the_host() -> None:
    """Run the real script against the real network.

    The fakes above check the decisions; this checks the thing that actually ships,
    because the whole probe rests on one measured fact — that .NET's Ping returns
    the locale-independent `PacketTooBig` where ping.exe prints a translated
    sentence and an exit code that cannot tell "too big" from "no answer".

    A machine with no route out is a real configuration, so None is accepted here.
    What is not accepted is a number outside the range the search can produce.
    """
    measured = path_mtu.probe_path_mtu()
    if measured is None:
        pytest.skip("no measurable path to either probe target from this host")
    assert 1280 <= measured <= 1500
    assert path_mtu.probe_path_mtu() == measured
