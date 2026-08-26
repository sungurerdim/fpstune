"""GPU command for fpstune CLI."""

from __future__ import annotations

import click
from rich.progress import Progress, SpinnerColumn, TextColumn

from fpstune.commands import presentation as ui
from fpstune.commands.scan import run_scan
from fpstune.settings.base import SettingCategory, SettingExecutor
from fpstune.utils.detect import get_gpu_info


def _is_gpu_setting(setting: SettingExecutor) -> bool:
    return setting.category == SettingCategory.GPU


@click.command()
def gpu() -> None:
    """Show how this GPU is configured, and what fpstune would change.

    Read-only. Applying is done from the browser, where each change shows what
    it costs as well as what it gains.
    """
    # Previously this command took --low-latency, --power and --vsync, applied
    # none of them, and printed a line pointing at the web UI. An option that is
    # accepted and ignored is worse than one that does not exist: `fpstune gpu
    # --power maximum` read as a machine that had been configured, and the
    # default it advertised was the one setting in this whole area that costs
    # heat for no frames. The options are gone; what is left is true.
    ui.print_banner()

    gpu_info = get_gpu_info()
    if gpu_info is None:
        ui.fail("No GPU detected")
        ui.hint(
            [
                "Check that a display driver is installed and the card is enumerated.",
                "Run 'fpstune status' to see what else could and could not be read.",
            ]
        )
        return

    ui.details(
        [
            ("GPU", gpu_info.name),
            ("Vendor", gpu_info.vendor.value),
            ("Driver", gpu_info.driver_version),
            ("VRAM", f"{gpu_info.vram_mb} MB"),
        ],
        title="This GPU",
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=ui.console,
        transient=True,
    ) as progress:
        progress.add_task("Reading GPU settings...", total=None)
        scan = run_scan(predicate=_is_gpu_setting)

    ui.blank()
    ui.heading("GPU settings")

    if not scan.readable:
        ui.warn("None of this GPU's settings could be read here")
        return

    for finding in scan.at_recommended:
        ui.ok(finding.setting.display_name, str(finding.result.value))
    for finding in scan.worth_changing:
        ui.step(
            finding.setting.display_name,
            f"{finding.result.value} → {finding.setting.recommended_value}",
        )

    ui.blank()
    if scan.worth_changing:
        ui.warn(scan.summary)
        ui.info("Run 'fpstune serve' to review and apply them")
    else:
        ui.ok(scan.summary)
