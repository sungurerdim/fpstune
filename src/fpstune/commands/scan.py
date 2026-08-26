"""Read this machine's settings once, for whatever wants to report on them.

`status` and `gpu` both answer "how is this machine set up right now", and both
used to answer it by printing a sentence telling the user to open the web UI.
The detection engine that could answer it properly was one import away.

One scan, several reports. The split matters because a scan is the expensive
half — a few seconds of registry reads, powercfg queries and driver lookups —
and the shaping is free. Anything that wants a different slice takes a
`predicate` rather than running its own scan.

Nothing here prints. A module that both measures and formats is a module you
cannot test without reading a terminal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from fpstune.settings.applicability import is_absent_reading
from fpstune.settings.base import DetectionResult, SettingExecutor
from fpstune.settings.detection import DetectionEngine
from fpstune.settings.hardware_context import build_hardware_context
from fpstune.settings.impact_categories import derive_impact_categories
from fpstune.settings.registry import SettingsRegistry


@dataclass(frozen=True)
class Finding:
    """One setting, and what this machine currently has it set to."""

    setting: SettingExecutor
    result: DetectionResult

    @property
    def at_recommended(self) -> bool:
        return self.result.is_optimized

    @property
    def readable(self) -> bool:
        """Whether the machine gave an answer at all.

        A sentinel like `not_installed` is a real answer about the world — the
        game is not here — and not a failure to read, so it is separated from
        both "set correctly" and "set wrongly". Counting it as either is how a
        machine with no games installed reports as badly tuned.
        """
        return self.result.success and not is_absent_reading(self.result.value)


@dataclass
class Scan:
    """Every applicable setting on this machine, and where it stands."""

    findings: list[Finding] = field(default_factory=list)
    skipped: int = 0
    """Settings that do not apply to this hardware at all — not a shortfall."""

    @property
    def readable(self) -> list[Finding]:
        return [f for f in self.findings if f.readable]

    @property
    def at_recommended(self) -> list[Finding]:
        return [f for f in self.readable if f.at_recommended]

    @property
    def worth_changing(self) -> list[Finding]:
        return [f for f in self.readable if not f.at_recommended]

    @property
    def unreadable(self) -> list[Finding]:
        return [f for f in self.findings if not f.readable]

    def by_category(self) -> dict[str, tuple[int, int]]:
        """Kind of gain -> (already right, worth changing).

        Keyed by the impact category rather than by the setting's own module, so
        the answer is "your latency is tuned, your heat is not" rather than a
        list of file names.
        """
        counts: dict[str, tuple[int, int]] = {}
        for finding in self.readable:
            for category in derive_impact_categories(finding.setting.impact_scores):
                right, wrong = counts.get(category, (0, 0))
                if finding.at_recommended:
                    counts[category] = (right + 1, wrong)
                else:
                    counts[category] = (right, wrong + 1)
        return counts

    @property
    def summary(self) -> str:
        """One line, and it leads with what is not done.

        A machine with 200 settings right and 40 wrong is a machine with 40
        things to do, and "200 optimized" is the wording that hides them.
        """
        total = len(self.readable)
        if not total:
            return "Nothing on this machine could be read"
        pending = len(self.worth_changing)
        if not pending:
            return f"All {total} readable settings are already at their recommended value"
        return f"{pending} of {total} readable settings are not at their recommended value"


def run_scan(
    *,
    predicate: Callable[[SettingExecutor], bool] | None = None,
    registry: SettingsRegistry | None = None,
) -> Scan:
    """Detect this machine's settings, optionally only some of them.

    `predicate` narrows what is *detected*, not what is reported, so a caller
    asking about GPU settings pays for GPU settings only.
    """
    registry = registry or SettingsRegistry()
    context = build_hardware_context()
    engine = DetectionEngine(hardware_context=context)

    wanted = [s for s in registry.get_all() if predicate is None or predicate(s)]
    results = engine.detect_all(wanted, hardware_context=context)

    scan = Scan()
    for setting in wanted:
        result = results.get(setting.id)
        if result is None:
            continue
        if not result.is_applicable:
            scan.skipped += 1
            continue
        scan.findings.append(Finding(setting=setting, result=result))
    return scan
