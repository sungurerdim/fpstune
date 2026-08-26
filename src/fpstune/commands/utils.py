"""Shared CLI utilities and display helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.table import Table

if TYPE_CHECKING:
    from fpstune.benchmark.furmark import FurMarkBenchmark, FurMarkResult
    from fpstune.benchmark.presentmon import BenchmarkCapture, PresentMonBenchmark

from fpstune.commands import presentation
from fpstune.utils.admin import elevate_if_needed, is_admin

# One Console for the whole CLI, and one banner. Both live in `presentation`,
# which owns everything fpstune puts on a terminal; these are re-exported so the
# six command modules that already import them from here keep working. Two
# Console objects would disagree about width and colour support, and two banners
# did disagree — the hand-drawn one here was a column wider than its own frame.
console = presentation.console
print_banner = presentation.print_banner


def check_admin() -> bool:
    """Check for admin privileges and warn if not present."""
    if not is_admin():
        console.print(
            "[bold red]Warning:[/] Administrator privileges required for most operations.",
            style="yellow",
        )
        console.print("Please run as Administrator.")
        return False
    return True


def require_admin_or_elevate() -> None:
    """Require admin privileges, prompting for UAC elevation if needed.

    On Windows: Shows UAC prompt if not running as admin.
    On Linux/macOS: Shows error message to use sudo.

    Exits the process if admin privileges cannot be obtained.
    """
    if is_admin():
        return

    # Try to elevate (shows UAC prompt on Windows)
    # If successful, elevate_if_needed() exits and re-launches with admin
    elevate_if_needed()

    # If we're still here, elevation failed or was denied
    console.print()
    console.print("[bold red]Error:[/] fpstune requires administrator privileges.")
    console.print()

    if sys.platform == "win32":
        console.print("To run fpstune:")
        console.print("  1. Right-click fpstune.exe or Command Prompt")
        console.print("  2. Select 'Run as administrator'")
        console.print()
        console.print("Or re-run and accept the UAC prompt.")
    else:
        console.print("To run fpstune:")
        console.print("  sudo fpstune")

    sys.exit(1)


def display_furmark_result(result: FurMarkResult) -> None:
    """Display FurMark benchmark result."""
    table = Table(title=f"GPU Benchmark: {result.name}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("[bold]Score[/]", f"[bold]{result.score:,}[/]")
    table.add_row("", "")
    table.add_row("Average FPS", f"{result.fps_avg:.1f}")
    table.add_row("Minimum FPS", f"{result.fps_min:.1f}")
    table.add_row("Maximum FPS", f"{result.fps_max:.1f}")
    table.add_row("", "")
    table.add_row("Resolution", result.resolution)
    table.add_row("API", result.api)
    table.add_row("MSAA", f"{result.msaa}x" if result.msaa else "Off")
    table.add_row("Duration", f"{result.duration_seconds}s")

    if result.gpu_name:
        table.add_row("", "")
        table.add_row("GPU", result.gpu_name)
    if result.gpu_driver:
        table.add_row("Driver", result.gpu_driver)
    if result.gpu_temp_max:
        table.add_row("Max Temp", f"{result.gpu_temp_max:.0f}\u00b0C")
    if result.gpu_power_max:
        table.add_row("Max Power", f"{result.gpu_power_max:.0f}W")

    console.print(table)


def load_furmark_result(fm: FurMarkBenchmark, name_or_path: str) -> FurMarkResult | None:
    """Load a FurMark result by name or path."""
    # Try as path first
    path = Path(name_or_path)
    if path.exists():
        return fm.load_result(path)

    # Search by name
    for result_path in fm.list_results():
        result = fm.load_result(result_path)
        if result and result.name == name_or_path:
            return result

    return None


def show_benchmark_comparison(fm: FurMarkBenchmark) -> None:
    """Show before/after benchmark comparison."""
    # Find before and after results
    before_result = None
    after_result = None

    for path in fm.list_results():
        result = fm.load_result(path)
        if result:
            if result.name == "before" and not before_result:
                before_result = result
            elif result.name == "after" and not after_result:
                after_result = result

    if not before_result:
        console.print("[yellow]No 'before' benchmark found.[/]")
        console.print("[dim]Run 'fpstune apply' to create a before/after comparison.[/]")
        return

    if not after_result:
        console.print("[yellow]No 'after' benchmark found.[/]")
        console.print("[dim]Run 'fpstune benchmark --after' after rebooting.[/]")
        return

    # Show comparison
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]PERFORMANCE COMPARISON[/]")
    console.print("=" * 60)

    comparison = fm.compare(before_result, after_result)

    comp_table = Table()
    comp_table.add_column("Metric", style="cyan")
    comp_table.add_column("Before", style="dim")
    comp_table.add_column("After", style="green")
    comp_table.add_column("Change")

    # Score
    score_change = comparison.score_improvement
    score_color = "green" if score_change > 0 else "red" if score_change < 0 else "dim"
    comp_table.add_row(
        "[bold]Score[/]",
        f"{before_result.score:,}",
        f"[bold]{after_result.score:,}[/]",
        f"[{score_color}]{score_change:+.1f}%[/{score_color}]",
    )

    # FPS
    fps_change = comparison.fps_improvement
    fps_color = "green" if fps_change > 0 else "red" if fps_change < 0 else "dim"
    comp_table.add_row(
        "Average FPS",
        f"{before_result.fps_avg:.1f}",
        f"{after_result.fps_avg:.1f}",
        f"[{fps_color}]{fps_change:+.1f}%[/{fps_color}]",
    )

    # Min FPS
    min_fps_change = comparison.min_fps_improvement
    min_color = "green" if min_fps_change > 0 else "red" if min_fps_change < 0 else "dim"
    comp_table.add_row(
        "Minimum FPS",
        f"{before_result.fps_min:.1f}",
        f"{after_result.fps_min:.1f}",
        f"[{min_color}]{min_fps_change:+.1f}%[/{min_color}]",
    )

    console.print(comp_table)

    # Summary
    best_improvement = max(score_change, fps_change, min_fps_change)
    if best_improvement > 5:
        console.print(
            f"\n[bold green]Excellent! Performance improved by up to {best_improvement:.1f}%[/]"
        )
    elif best_improvement > 0:
        console.print(f"\n[green]Performance improved by {best_improvement:.1f}%[/]")
    elif best_improvement < -5:
        console.print(f"\n[bold red]Performance decreased by {abs(best_improvement):.1f}%[/]")
        console.print("[dim]Consider reverting changes with 'fpstune revert --all'[/]")
    else:
        console.print("\n[yellow]No significant performance change detected[/]")


def display_fps_stats(capture: BenchmarkCapture) -> None:
    """Display FPS statistics in a table."""
    stats = capture.stats

    # Main stats table
    table = Table(title=f"FPS Results: {capture.name} ({capture.game_name})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Duration", f"{stats.duration_seconds:.1f} seconds")
    table.add_row("Total Frames", str(stats.frame_count))
    table.add_row("", "")
    table.add_row("[bold]Average FPS[/]", f"[bold]{stats.fps_avg:.1f}[/]")
    table.add_row("Minimum FPS", f"{stats.fps_min:.1f}")
    table.add_row("Maximum FPS", f"{stats.fps_max:.1f}")
    table.add_row("[yellow]1% Low FPS[/]", f"[yellow]{stats.fps_1_percent_low:.1f}[/]")
    table.add_row("[yellow]0.1% Low FPS[/]", f"[yellow]{stats.fps_0_1_percent_low:.1f}[/]")
    table.add_row("", "")
    table.add_row("Avg Frame Time", f"{stats.frametime_avg:.2f} ms")
    table.add_row("99th Percentile", f"{stats.frametime_99th:.2f} ms")
    table.add_row("Std Deviation", f"{stats.frametime_stdev:.2f} ms")
    table.add_row("", "")
    table.add_row("Stutter Count", str(stats.stutter_count))
    table.add_row("Stutter %", f"{stats.stutter_percent:.1f}%")

    console.print(table)


def load_fps_capture(pm: PresentMonBenchmark, name_or_path: str) -> BenchmarkCapture | None:
    """Load an FPS capture by name or path."""
    # Try as path first
    path = Path(name_or_path)
    if path.exists():
        return pm.load_capture(path)

    # Search by name
    for capture_path in pm.list_captures():
        if capture_path.suffix == ".json":
            capture = pm.load_capture(capture_path)
            if capture and capture.name == name_or_path:
                return capture

    return None


def display_network_result(result: Any) -> None:
    """Display network benchmark result."""
    table = Table(title=f"Network Benchmark: {result.name}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Target", result.target)
    table.add_row("", "")
    table.add_row("[bold]Ping Statistics[/]", "")
    table.add_row("  Average", f"{result.stats.ping_avg:.2f} ms")
    table.add_row("  Minimum", f"{result.stats.ping_min:.2f} ms")
    table.add_row("  Maximum", f"{result.stats.ping_max:.2f} ms")
    table.add_row("  Std Dev", f"{result.stats.ping_stdev:.2f} ms")
    table.add_row("  Packet Loss", f"{result.stats.ping_loss_percent:.1f}%")
    table.add_row("", "")

    if result.stats.tcp_count > 0:
        table.add_row("[bold]TCP Connection[/]", "")
        table.add_row("  Average", f"{result.stats.tcp_avg:.2f} ms")
        table.add_row("  Minimum", f"{result.stats.tcp_min:.2f} ms")
        table.add_row("  Maximum", f"{result.stats.tcp_max:.2f} ms")
        table.add_row("", "")

    table.add_row("[bold]Jitter[/]", "")
    table.add_row("  Average", f"{result.stats.jitter_avg:.2f} ms")
    table.add_row("  Maximum", f"{result.stats.jitter_max:.2f} ms")

    console.print(table)


def load_network_result(nb: Any, name_or_path: str) -> Any:
    """Load a network result by name or path."""
    path = Path(name_or_path)
    if path.exists():
        return nb.load_result(path)

    for result_path in nb.list_results():
        result = nb.load_result(result_path)
        if result and result.name == name_or_path:
            return result

    return None


def display_dpc_result(result: Any) -> None:
    """Display DPC benchmark result."""
    table = Table(title=f"DPC Benchmark: {result.name}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("[bold]Timer Resolution[/]", "")
    table.add_row("  Current", f"{result.stats.timer_resolution_ms:.4f} ms")
    table.add_row("  In Nanoseconds", f"{result.stats.timer_resolution_ns:,} ns")
    table.add_row("", "")

    table.add_row("[bold]Sleep Accuracy[/]", "")
    table.add_row("  Average Overshoot", f"{result.stats.sleep_accuracy_avg_us:.2f} us")
    table.add_row("  Maximum Overshoot", f"{result.stats.sleep_accuracy_max_us:.2f} us")
    table.add_row("  Std Deviation", f"{result.stats.sleep_accuracy_stdev_us:.2f} us")
    table.add_row("", "")

    table.add_row("[bold]Timing Jitter[/]", "")
    table.add_row("  Average", f"{result.stats.timing_jitter_avg_us:.2f} us")
    table.add_row("  Maximum", f"{result.stats.timing_jitter_max_us:.2f} us")
    table.add_row("", "")

    table.add_row("QPC Resolution", f"{result.stats.qpc_resolution_ns:.2f} ns")
    table.add_row("Sample Count", str(result.stats.sample_count))

    console.print(table)


def load_dpc_result(db: Any, name_or_path: str) -> Any:
    """Load a DPC result by name or path."""
    path = Path(name_or_path)
    if path.exists():
        return db.load_result(path)

    for result_path in db.list_results():
        result = db.load_result(result_path)
        if result and result.name == name_or_path:
            return result

    return None
