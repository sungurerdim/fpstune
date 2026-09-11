"""Seven settings steer a control loop modern silicon is not running.

Microsoft's processor power management tuning document — already the source
these settings cite — says of Intel Broadwell-and-later under Windows' default
HWP configuration:

    "most of the processor power management decisions are made in the processor
    instead of OS level ... The legacy PPM parameters used by OS have minimal
    impact on the actual frequency decisions, except telling the processor if it
    should favor power or performance, or capping the minimal and maximum
    frequencies."

and, on the same page, "OS is no longer required to monitor activity and select
frequency at regular intervals". Its own tuning list splits accordingly: under
"For HWP enabled system" it names Energy performance preference alone, and the
six increase/decrease threshold, time and policy parameters sit under "For
Non-HWP system". The time-check interval is the period of exactly that
monitoring loop, so it is the seventh.

Whether the loop runs here is not a guess: `PERFAUTONOMOUS`
(8baa4a8a-14c6-4451-8e8b-14bdbd197537) is one read. C10 makes the answer
first-class — "a setting that cannot apply reports an ABSENT_READINGS sentinel
-> is_applicable=False" — rather than showing a control that does nothing while
claiming `fps_cpu_bound` and `latency_ms`.

Two things this file pins that are easy to get wrong:

  - the question is the *effective* value, so it is asked of powercfg, not of the
    plan's own registry key. Measured 2026-09-11: the active plan holds no
    override for PERFAUTONOMOUS and its Balanced catalogue default is 0, yet
    `powercfg /qh` reports 0x00000001. A registry-only read would have answered
    "not autonomous" on a machine that is.
  - an unreadable answer leaves every setting visible. Hiding a tweak because a
    subprocess failed is a worse error than showing one that does little.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fpstune.settings.applicability import ABSENT_READINGS, is_absent_reading
from fpstune.settings.definitions.power import (
    POWER_CPU_DECREASE_POLICY,
    POWER_CPU_DECREASE_THRESHOLD,
    POWER_CPU_DECREASE_TIME,
    POWER_CPU_EPP,
    POWER_CPU_INCREASE_POLICY,
    POWER_CPU_INCREASE_THRESHOLD,
    POWER_CPU_INCREASE_TIME,
    POWER_CPU_MAX_STATE,
    POWER_CPU_MIN_PARKING,
    POWER_CPU_MIN_STATE,
    POWER_CPU_PERF_CHECK,
)
from fpstune.settings.executors.powercfg import (
    _AUTONOMOUS_BYPASSED_SETTINGS,
    PowerCfgExecutor,
)

# What powercfg prints for PERFAUTONOMOUS. Only the hex matters — the friendly
# names arrive in the system language, which is why nothing here reads them.
_QUERY_OUTPUT = """
Power Setting GUID: 8baa4a8a-14c6-4451-8e8b-14bdbd197537
  GUID Alias: PERFAUTONOMOUS
  Possible Setting Index: 000
  Possible Setting Index: 001
  Current AC Power Setting Index: 0x0000000{index}
  Current DC Power Setting Index: 0x0000000{index}
"""

BYPASSED = [
    POWER_CPU_INCREASE_THRESHOLD,
    POWER_CPU_DECREASE_THRESHOLD,
    POWER_CPU_INCREASE_POLICY,
    POWER_CPU_DECREASE_POLICY,
    POWER_CPU_PERF_CHECK,
    POWER_CPU_INCREASE_TIME,
    POWER_CPU_DECREASE_TIME,
]

# What HWP leaves in the OS's hands, per the same document: the preference and
# the two frequency caps. Core parking is a scheduling decision, not a frequency
# one, so it stays as well.
STILL_EFFECTIVE = [
    POWER_CPU_EPP,
    POWER_CPU_MIN_STATE,
    POWER_CPU_MAX_STATE,
    POWER_CPU_MIN_PARKING,
]


@pytest.fixture
def executor() -> PowerCfgExecutor:
    # The answer is cached for the process, so a test must not inherit another
    # test's machine.
    PowerCfgExecutor.invalidate_cache()
    yield PowerCfgExecutor()
    PowerCfgExecutor.invalidate_cache()


def _autonomous(index: int):
    """Patch powercfg to answer with the given PERFAUTONOMOUS index."""
    return patch.object(
        PowerCfgExecutor, "_run", return_value=(True, _QUERY_OUTPUT.format(index=index))
    )


def _unreadable():
    return patch.object(PowerCfgExecutor, "_run", return_value=(False, "access denied"))


class TestWhenTheProcessorDecides:
    @pytest.mark.parametrize("setting", BYPASSED, ids=lambda s: s.id)
    def test_a_bypassed_setting_reports_itself_absent(self, executor, setting) -> None:
        with _autonomous(1):
            value, error = executor.detect(setting)

        assert error is None
        assert is_absent_reading(value), (
            f"{setting.id} answered {value!r} on a machine whose processor is choosing its "
            "own frequencies. C10: not-applicable is a first-class answer."
        )

    @pytest.mark.parametrize("setting", BYPASSED, ids=lambda s: s.id)
    def test_it_uses_a_spelling_the_engine_already_knows(self, executor, setting) -> None:
        """Never a locally invented sentinel — `applicability.ABSENT_READINGS` is the set."""
        with _autonomous(1):
            value, _ = executor.detect(setting)

        assert value in ABSENT_READINGS

    @pytest.mark.parametrize("setting", STILL_EFFECTIVE, ids=lambda s: s.id)
    def test_what_hwp_still_honours_keeps_reporting(self, executor, setting) -> None:
        with (
            _autonomous(1),
            patch.object(PowerCfgExecutor, "_detect_via_registry_key", return_value=33),
        ):
            value, error = executor.detect(setting)

        assert (value, error) == (33, None)

    def test_the_gated_set_is_exactly_these_seven_settings(self) -> None:
        """A GUID in the executor that no shipped setting uses gates nothing.

        The set lives in the executor and the GUIDs live in the definitions, so
        without this they can drift apart in silence — the defect that let four
        settings point at GUIDs Windows does not publish.
        """
        assert {s.detect_args["setting"] for s in BYPASSED} == _AUTONOMOUS_BYPASSED_SETTINGS
        for setting in STILL_EFFECTIVE:
            assert setting.detect_args["setting"] not in _AUTONOMOUS_BYPASSED_SETTINGS

    def test_it_asks_powercfg_for_the_effective_value(self, executor) -> None:
        """The plan holds no override here and the effective value is still 1."""
        calls: list[str] = []

        def run(_self, args: str):
            calls.append(args)
            return True, _QUERY_OUTPUT.format(index=1)

        with patch.object(PowerCfgExecutor, "_run", run):
            executor.detect(POWER_CPU_INCREASE_POLICY)

        assert calls, "nothing was asked"
        assert calls[0].startswith("/qh SCHEME_CURRENT ")
        assert "8baa4a8a-14c6-4451-8e8b-14bdbd197537" in calls[0]

    def test_the_answer_is_read_once_for_the_whole_scan(self, executor) -> None:
        """C7: never a subprocess per setting for something that cannot change mid-scan."""
        calls: list[str] = []

        def run(_self, args: str):
            calls.append(args)
            return True, _QUERY_OUTPUT.format(index=1)

        with patch.object(PowerCfgExecutor, "_run", run):
            for setting in BYPASSED:
                executor.detect(setting)

        assert len(calls) == 1, f"asked powercfg {len(calls)} times for one machine fact"


class TestWhenWindowsDecides:
    @pytest.mark.parametrize("setting", BYPASSED, ids=lambda s: s.id)
    def test_a_bypassed_setting_still_reports_on_a_non_hwp_machine(self, executor, setting) -> None:
        """Autonomous mode off: Windows runs the loop, so all seven act."""
        with (
            _autonomous(0),
            patch.object(PowerCfgExecutor, "_detect_via_registry_key", return_value=15),
        ):
            value, error = executor.detect(setting)

        assert (value, error) == (15, None)

    @pytest.mark.parametrize("setting", BYPASSED, ids=lambda s: s.id)
    def test_an_unreadable_answer_hides_nothing(self, executor, setting) -> None:
        """A failed subprocess must not make seven tweaks disappear."""
        with (
            _unreadable(),
            patch.object(PowerCfgExecutor, "_detect_via_registry_key", return_value=15),
        ):
            value, error = executor.detect(setting)

        assert (value, error) == (15, None)
