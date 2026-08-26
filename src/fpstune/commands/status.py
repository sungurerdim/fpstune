"""Status command for fpstune CLI."""

from __future__ import annotations

import click
from rich.progress import Progress, SpinnerColumn, TextColumn

from fpstune.commands import presentation as ui
from fpstune.commands.scan import Scan, run_scan
from fpstune.utils.admin import is_admin
from fpstune.utils.detect import get_gpu_info, get_os_info

# How many individual settings to name before saying "and N more". A status
# command that prints ninety rows is one nobody reads to the end.
_NAMED_LIMIT = 8


def _describe_machine() -> list[tuple[str, str]]:
    os_info = get_os_info()
    gpu_info = get_gpu_info()

    rows = [
        ("OS", os_info.edition),
        ("Version", f"{os_info.version} (build {os_info.build})"),
    ]
    if not os_info.is_supported:
        rows.append(("Supported", "no — fpstune targets Windows 11"))
    if gpu_info:
        rows.append(("GPU", f"{gpu_info.name}  {gpu_info.vram_mb} MB"))
        rows.append(("Driver", gpu_info.driver_version))
    rows.append(("Elevated", "yes" if is_admin() else "no — some settings cannot be read"))
    return rows


def _report(scan: Scan) -> None:
    ui.blank()
    ui.heading("Where this machine stands")

    if not scan.readable:
        ui.warn(scan.summary)
        return

    if scan.worth_changing:
        ui.warn(scan.summary)
    else:
        ui.ok(scan.summary)

    ui.blank()
    rows = []
    for category, (right, wrong) in sorted(
        scan.by_category().items(), key=lambda item: -item[1][1]
    ):
        total = right + wrong
        rows.append((category, f"{wrong} of {total} still to do" if wrong else f"all {total} done"))
    if rows:
        ui.details(rows, title="By the kind of gain")

    if scan.worth_changing:
        ui.blank()
        ui.heading("Not at the recommended value")
        for finding in scan.worth_changing[:_NAMED_LIMIT]:
            ui.step(
                finding.setting.display_name,
                f"{finding.result.value} → {finding.setting.recommended_value}",
            )
        remaining = len(scan.worth_changing) - _NAMED_LIMIT
        if remaining > 0:
            ui.info(f"and {remaining} more")

    # Counted separately and stated plainly: a setting whose value could not be
    # read is neither tuned nor untuned, and rolling it into either number is how
    # a status report starts flattering the machine it is describing.
    if scan.unreadable:
        ui.blank()
        ui.info(
            f"{len(scan.unreadable)} settings could not be read here",
            "absent hardware, an uninstalled game, or a value this machine does not expose",
        )
    if scan.skipped:
        ui.info(f"{scan.skipped} settings do not apply to this hardware")


@click.command()
def status() -> None:
    """Show what this machine is set to, and what is left to do."""
    ui.print_banner()
    ui.details(_describe_machine(), title="This machine")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=ui.console,
        transient=True,
    ) as progress:
        progress.add_task("Reading this machine's settings...", total=None)
        scan = run_scan()

    _report(scan)

    ui.blank()
    ui.info("Run 'fpstune serve' to review and apply these from the browser")
