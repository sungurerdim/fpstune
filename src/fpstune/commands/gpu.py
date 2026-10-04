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


@click.command("nvidia-dump")
def nvidia_dump() -> None:
    """Save every NVIDIA global driver setting to a file, for diagnosis.

    Read-only. Run it, change one option in NVIDIA Control Panel, run it again,
    and the two files show exactly which driver keys that option writes.
    """
    import json
    from datetime import datetime

    from fpstune.core.nv_drs import KEYS
    from fpstune.core.nvapi import NvapiError, NvapiUnavailable, dump_driver_settings
    from fpstune.utils.config import get_config_dir

    try:
        settings = dump_driver_settings()
    except NvapiUnavailable as exc:
        ui.fail("NVIDIA driver settings could not be opened", str(exc))
        return
    except NvapiError as exc:
        ui.fail("The NVIDIA driver refused to list its settings", str(exc))
        return

    names = {setting_id: key.key for key in KEYS.values() for setting_id in key.ids}
    rows = [
        {
            "id": f"{item.setting_id:#010x}",
            "value": f"{item.value:#010x}",
            "location": item.location,
            "predefined": item.predefined,
            "fpstune_key": names.get(item.setting_id),
        }
        for item in sorted(settings, key=lambda s: s.setting_id)
    ]

    out_dir = get_config_dir() / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"nvidia-dump-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    ui.ok(f"{len(rows)} driver settings saved", str(path))
