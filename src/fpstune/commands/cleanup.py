"""Cleanup command for fpstune CLI."""

from __future__ import annotations

import sys

import click
from rich.progress import Progress, SpinnerColumn, TextColumn

from fpstune.commands import presentation as ui
from fpstune.commands.utils import check_admin


@click.command()
def cleanup() -> None:
    """Free disk space by clearing temporary files and superseded components."""
    ui.print_banner()

    if not check_admin():
        sys.exit(1)

    from fpstune.core.dism import Dism

    dism = Dism()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=ui.console,
        transient=True,
    ) as progress:
        progress.add_task("Clearing temporary files and component store...", total=None)
        temp_result = dism.clean_temp_files()
        dism_result = dism.component_cleanup()

    freed = temp_result.space_freed_mb + dism_result.space_freed_mb
    ui.heading("Cleanup")

    # Reported per stage rather than as one number, because the two fail
    # independently: a component cleanup that fails while temp files succeed
    # used to surface as a single yellow line with a total that looked fine.
    for label, result in (("Temporary files", temp_result), ("Component store", dism_result)):
        report = ui.ok if result.success else ui.warn
        report(label, f"{result.space_freed_mb} MB freed")

    ui.blank()
    if temp_result.success and dism_result.success:
        ui.ok(f"Freed {freed} MB")
    else:
        ui.warn(f"Freed {freed} MB", "one stage did not finish — details below")

    details = temp_result.details + dism_result.details
    if details:
        ui.blank()
        for detail in details:
            ui.info(detail)
