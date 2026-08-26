"""Benchmark commands for fpstune CLI (benchmark, fps, gpu-bench, dpc-bench, network-bench)."""

from __future__ import annotations

from pathlib import Path

import click
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from fpstune.benchmark.furmark import FURMARK_DOWNLOAD_SIZE_MB, FurMarkBenchmark
from fpstune.benchmark.presentmon import PRESENTMON_DOWNLOAD_SIZE_MB, PresentMonBenchmark
from fpstune.commands.utils import (
    console,
    display_dpc_result,
    display_fps_stats,
    display_furmark_result,
    display_network_result,
    load_dpc_result,
    load_fps_capture,
    load_furmark_result,
    load_network_result,
    print_banner,
    show_benchmark_comparison,
)

# ============================================================================
# benchmark command (standalone)
# ============================================================================


@click.command()
@click.option(
    "--after", is_flag=True, help="Run post-optimization benchmark and compare with 'before'"
)
@click.option(
    "--preset",
    "-p",
    type=click.Choice(["quick", "standard"]),
    default="quick",
    help="Benchmark preset",
)
@click.option("--compare", is_flag=True, help="Compare before/after results without running")
def benchmark(
    after: bool,
    preset: str,
    compare: bool,
) -> None:
    """Run GPU benchmark with FurMark 2.

    By default, runs a quick benchmark to measure current GPU performance.
    Use --after flag after rebooting to compare with pre-optimization results.

    \b
    Examples:
      fpstune benchmark           # Run quick benchmark
      fpstune benchmark --after   # Run after reboot, compare with 'before'
      fpstune benchmark --compare # Just show comparison
    """
    print_banner()

    fm = FurMarkBenchmark()

    # Auto-install FurMark if needed
    if not compare and not fm.is_installed():
        console.print(
            f"[yellow]FurMark 2 not installed. Downloading (~{FURMARK_DOWNLOAD_SIZE_MB} MB)...[/]"
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading FurMark 2...", total=100)

            def update_progress(pct: int) -> None:
                progress.update(task, completed=pct)

            if not fm.install(progress_callback=update_progress):
                console.print("[red]\u2717[/] Failed to install FurMark 2")
                return
            console.print("[green]\u2713[/] FurMark 2 installed")

    # Just show comparison?
    if compare:
        show_benchmark_comparison(fm)
        return

    # Run benchmark
    name = "after" if after else "benchmark"
    settings = fm.get_presets()[preset]

    console.print(f"\nRunning {preset} GPU benchmark ({settings['duration']}s)...")
    console.print(f"Resolution: {settings['resolution']}, MSAA: {settings['msaa']}x\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Benchmarking ({settings['duration']}s)...", total=None)
        result = fm.run_benchmark(name=name, preset=preset)

    if not result:
        console.print("[red]\u2717[/] Benchmark failed")
        return

    fm.save_result(result)

    # Show result
    display_furmark_result(result)

    # If --after, compare with before
    if after:
        show_benchmark_comparison(fm)


# ============================================================================
# fps command group (PresentMon-based)
# ============================================================================


@click.group()
def fps() -> None:
    """FPS benchmarking with PresentMon.

    Capture and analyze real game frame times for before/after comparison.
    """
    pass


@fps.command("install")
def fps_install() -> None:
    """Install PresentMon (auto-download from GitHub)."""
    pm = PresentMonBenchmark()

    if pm.is_installed():
        console.print("[green]\u2713[/] PresentMon is already installed")
        console.print(f"  Location: {pm.presentmon_path}")
        return

    console.print("Downloading PresentMon...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading...", total=100)

        def update_progress(pct: int) -> None:
            progress.update(task, completed=pct)

        if pm.install(progress_callback=update_progress):
            console.print("[green]\u2713[/] PresentMon installed successfully")
            console.print(f"  Location: {pm.presentmon_path}")
        else:
            console.print("[red]\u2717[/] Failed to install PresentMon")


@fps.command("start")
@click.option("--game", "-g", help="Game process name (e.g., 'game.exe')")
@click.option(
    "--duration", "-d", default=0, type=int, help="Capture duration in seconds (0=until stopped)"
)
@click.option("--name", "-n", default=None, help="Name for this capture")
def fps_start(game: str | None, duration: int, name: str | None) -> None:
    """Start FPS capture (run this while gaming)."""
    pm = PresentMonBenchmark()

    if not pm.is_installed():
        console.print(
            f"[yellow]PresentMon not installed. Installing (~{PRESENTMON_DOWNLOAD_SIZE_MB} MB)...[/]"
        )
        if not pm.install():
            console.print("[red]\u2717[/] Failed to install PresentMon")
            return

    if pm.is_capturing():
        console.print("[yellow]A capture is already in progress[/]")
        console.print("Use 'fpstune fps stop' to stop it first")
        return

    if pm.start_capture(process_name=game, output_name=name, duration_seconds=duration):
        console.print("[green]\u2713[/] FPS capture started")
        if game:
            console.print(f"  Target: {game}")
        if duration > 0:
            console.print(f"  Duration: {duration} seconds")
        console.print("\n[dim]Play your game, then run 'fpstune fps stop' when done[/]")
    else:
        console.print("[red]\u2717[/] Failed to start capture")


@fps.command("stop")
@click.option("--name", "-n", default="capture", help="Name for this benchmark")
@click.option("--game-name", "-g", default="Unknown", help="Name of the game")
@click.option("--notes", default="", help="Additional notes")
def fps_stop(name: str, game_name: str, notes: str) -> None:
    """Stop FPS capture and analyze results."""
    pm = PresentMonBenchmark()

    if not pm.is_capturing():
        console.print("[yellow]No capture in progress[/]")
        return

    console.print("Stopping capture...")
    capture_file = pm.stop_capture()

    if not capture_file:
        console.print("[red]\u2717[/] No capture data found")
        return

    console.print(f"[green]\u2713[/] Capture saved: {capture_file}")

    # Analyze
    console.print("\nAnalyzing frame data...")
    capture = pm.create_capture(
        name=name,
        game_name=game_name,
        capture_file=capture_file,
        notes=notes,
    )

    if not capture:
        console.print("[red]\u2717[/] Failed to analyze capture")
        return

    # Save
    saved_path = pm.save_capture(capture)
    console.print(f"[green]\u2713[/] Benchmark saved: {saved_path}")

    # Display results
    display_fps_stats(capture)


@fps.command("analyze")
@click.argument("capture_file", type=click.Path(exists=True))
@click.option("--name", "-n", default="capture", help="Name for this benchmark")
@click.option("--game-name", "-g", default="Unknown", help="Name of the game")
def fps_analyze(capture_file: str, name: str, game_name: str) -> None:
    """Analyze an existing PresentMon CSV capture file."""
    pm = PresentMonBenchmark()

    console.print(f"Analyzing: {capture_file}")

    capture = pm.create_capture(
        name=name,
        game_name=game_name,
        capture_file=Path(capture_file),
    )

    if not capture:
        console.print("[red]\u2717[/] Failed to analyze capture")
        return

    saved_path = pm.save_capture(capture)
    console.print(f"[green]\u2713[/] Benchmark saved: {saved_path}")

    display_fps_stats(capture)


@fps.command("compare")
@click.option("--before", "-b", required=True, help="Before benchmark file or name")
@click.option("--after", "-a", required=True, help="After benchmark file or name")
def fps_compare(before: str, after: str) -> None:
    """Compare before/after FPS benchmarks."""
    pm = PresentMonBenchmark()

    # Load captures
    before_capture = load_fps_capture(pm, before)
    after_capture = load_fps_capture(pm, after)

    if not before_capture:
        console.print(f"[red]\u2717[/] Could not load 'before' benchmark: {before}")
        return

    if not after_capture:
        console.print(f"[red]\u2717[/] Could not load 'after' benchmark: {after}")
        return

    # Compare
    comparison = pm.compare(before_capture, after_capture)

    # Display report
    console.print(comparison.format_report())


@fps.command("list")
@click.option("--limit", "-l", default=10, help="Number of captures to show")
def fps_list(limit: int) -> None:
    """List saved FPS benchmarks."""
    pm = PresentMonBenchmark()
    captures = pm.list_captures()

    if not captures:
        console.print("No saved benchmarks found")
        console.print("\nRun 'fpstune fps start' to begin capturing")
        return

    table = Table(title="FPS Benchmarks")
    table.add_column("Name", style="cyan")
    table.add_column("Game")
    table.add_column("Avg FPS", style="green")
    table.add_column("1% Low", style="yellow")
    table.add_column("Date")

    for path in captures[:limit]:
        if path.suffix == ".json":
            capture = pm.load_capture(path)
            if capture:
                table.add_row(
                    capture.name,
                    capture.game_name,
                    f"{capture.stats.fps_avg:.1f}",
                    f"{capture.stats.fps_1_percent_low:.1f}",
                    capture.timestamp[:10] if capture.timestamp else "",
                )
        elif path.suffix == ".csv":
            # Raw CSV, not yet analyzed
            table.add_row(
                path.stem,
                "[dim]Not analyzed[/]",
                "-",
                "-",
                "",
            )

    console.print(table)


# ============================================================================
# gpu-bench command group (FurMark-based)
# ============================================================================


@click.group("gpu-bench")
def gpu_bench() -> None:
    """GPU benchmarking with FurMark 2.

    Run standardized GPU benchmarks for before/after comparison.
    """
    pass


@gpu_bench.command("install")
def gpu_bench_install() -> None:
    """Install FurMark 2 (auto-download)."""
    fm = FurMarkBenchmark()

    if fm.is_installed():
        console.print("[green]\u2713[/] FurMark 2 is already installed")
        console.print(f"  Location: {fm.furmark_cli_path}")
        return

    console.print("Downloading FurMark 2...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading...", total=100)

        def update_progress(pct: int) -> None:
            progress.update(task, completed=pct)

        if fm.install(progress_callback=update_progress):
            console.print("[green]\u2713[/] FurMark 2 installed successfully")
            console.print(f"  Location: {fm.furmark_cli_path}")
        else:
            console.print("[red]\u2717[/] Failed to install FurMark 2")


@gpu_bench.command("run")
@click.option("--name", "-n", default="benchmark", help="Name for this benchmark")
@click.option(
    "--preset",
    "-p",
    type=click.Choice(["quick", "standard", "extreme"]),
    default="standard",
    help="Benchmark preset",
)
@click.option(
    "--api", "-a", type=click.Choice(["opengl", "vulkan"]), default="opengl", help="Graphics API"
)
@click.option("--duration", "-d", type=int, help="Override duration (seconds)")
@click.option("--resolution", "-r", help="Override resolution (e.g., 1920x1080)")
def gpu_bench_run(
    name: str,
    preset: str,
    api: str,
    duration: int | None,
    resolution: str | None,
) -> None:
    """Run a GPU benchmark."""
    fm = FurMarkBenchmark()

    if not fm.is_installed():
        console.print("[yellow]FurMark 2 not installed. Installing...[/]")
        if not fm.install():
            console.print("[red]\u2717[/] Failed to install FurMark 2")
            return

    # Show settings
    settings = fm.get_presets()[preset]
    actual_duration = duration or settings["duration"]
    actual_resolution = resolution or settings["resolution"]

    console.print(f"\n[bold]Running GPU Benchmark: {name}[/]")
    console.print(f"  Preset: {preset}")
    console.print(f"  API: {api.upper()}")
    console.print(f"  Resolution: {actual_resolution}")
    console.print(f"  Duration: {actual_duration} seconds")
    console.print("")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Running benchmark ({actual_duration}s)...", total=None)

        result = fm.run_benchmark(
            name=name,
            preset=preset,
            api=api,
            custom_duration=duration,
            custom_resolution=resolution,
        )

    if not result:
        console.print("[red]\u2717[/] Benchmark failed")
        return

    # Save result
    saved_path = fm.save_result(result)
    console.print(f"[green]\u2713[/] Benchmark saved: {saved_path}")

    # Display results
    display_furmark_result(result)


@gpu_bench.command("compare")
@click.option("--before", "-b", required=True, help="Before benchmark name or file")
@click.option("--after", "-a", required=True, help="After benchmark name or file")
def gpu_bench_compare(before: str, after: str) -> None:
    """Compare before/after GPU benchmarks."""
    fm = FurMarkBenchmark()

    # Load results
    before_result = load_furmark_result(fm, before)
    after_result = load_furmark_result(fm, after)

    if not before_result:
        console.print(f"[red]\u2717[/] Could not load 'before' benchmark: {before}")
        return

    if not after_result:
        console.print(f"[red]\u2717[/] Could not load 'after' benchmark: {after}")
        return

    # Compare
    comparison = fm.compare(before_result, after_result)

    # Display report
    console.print(comparison.format_report())


@gpu_bench.command("list")
@click.option("--limit", "-l", default=10, help="Number of results to show")
def gpu_bench_list(limit: int) -> None:
    """List saved GPU benchmarks."""
    fm = FurMarkBenchmark()
    results = fm.list_results()

    if not results:
        console.print("No saved benchmarks found")
        console.print("\nRun 'fpstune gpu-bench run' to start benchmarking")
        return

    table = Table(title="GPU Benchmarks (FurMark)")
    table.add_column("Name", style="cyan")
    table.add_column("Score", style="green")
    table.add_column("Avg FPS", style="yellow")
    table.add_column("Resolution")
    table.add_column("API")
    table.add_column("Date")

    for path in results[:limit]:
        result = fm.load_result(path)
        if result:
            table.add_row(
                result.name,
                f"{result.score:,}",
                f"{result.fps_avg:.1f}",
                result.resolution,
                result.api,
                result.timestamp[:10] if result.timestamp else "",
            )

    console.print(table)


@gpu_bench.command("presets")
def gpu_bench_presets() -> None:
    """Show available benchmark presets."""
    fm = FurMarkBenchmark()
    presets = fm.get_presets()

    table = Table(title="FurMark Benchmark Presets")
    table.add_column("Preset", style="cyan")
    table.add_column("Duration")
    table.add_column("Resolution")
    table.add_column("MSAA")
    table.add_column("Use Case")

    table.add_row(
        "quick",
        f"{presets['quick']['duration']}s",
        presets["quick"]["resolution"],
        str(presets["quick"]["msaa"]),
        "Fast test, basic comparison",
    )
    table.add_row(
        "standard",
        f"{presets['standard']['duration']}s",
        presets["standard"]["resolution"],
        f"{presets['standard']['msaa']}x",
        "Recommended for most tests",
    )
    table.add_row(
        "extreme",
        f"{presets['extreme']['duration']}s",
        presets["extreme"]["resolution"],
        f"{presets['extreme']['msaa']}x",
        "High-end GPU stress test",
    )

    console.print(table)


# ============================================================================
# network-bench command group
# ============================================================================


@click.group("network-bench")
def network_bench() -> None:
    """Network latency benchmarking.

    Measure network latency before/after applying network optimizations.
    Tests both ICMP ping and TCP connection latency.
    """
    pass


@network_bench.command("run")
@click.option("--name", "-n", default="benchmark", help="Name for this benchmark")
@click.option("--target", "-t", default="8.8.8.8", help="Target IP or hostname")
@click.option("--pings", "-p", default=50, type=int, help="Number of pings")
@click.option("--tcp-count", default=20, type=int, help="Number of TCP connection tests")
def network_bench_run(name: str, target: str, pings: int, tcp_count: int) -> None:
    """Run a network latency benchmark."""
    from fpstune.benchmark.network import NetworkBenchmark

    nb = NetworkBenchmark()

    console.print(f"\n[bold]Running Network Latency Benchmark: {name}[/]")
    console.print(f"  Target: {target}")
    console.print(f"  Pings: {pings}, TCP tests: {tcp_count}")
    console.print("")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Testing network latency...", total=100)

        def update_progress(pct: int) -> None:
            progress.update(task, completed=pct)

        result = nb.run_benchmark(
            name=name,
            target=target,
            ping_count=pings,
            tcp_count=tcp_count,
            progress_callback=update_progress,
        )

    if not result:
        console.print("[red]\u2717[/] Benchmark failed")
        return

    # Save result
    saved_path = nb.save_result(result)
    console.print(f"[green]\u2713[/] Benchmark saved: {saved_path}")

    # Display results
    display_network_result(result)


@network_bench.command("compare")
@click.option("--before", "-b", required=True, help="Before benchmark name or file")
@click.option("--after", "-a", required=True, help="After benchmark name or file")
def network_bench_compare(before: str, after: str) -> None:
    """Compare before/after network benchmarks."""
    from fpstune.benchmark.network import NetworkBenchmark

    nb = NetworkBenchmark()

    before_result = load_network_result(nb, before)
    after_result = load_network_result(nb, after)

    if not before_result:
        console.print(f"[red]\u2717[/] Could not load 'before' benchmark: {before}")
        return

    if not after_result:
        console.print(f"[red]\u2717[/] Could not load 'after' benchmark: {after}")
        return

    comparison = nb.compare(before_result, after_result)
    console.print(comparison.format_report())


@network_bench.command("list")
@click.option("--limit", "-l", default=10, help="Number of results to show")
def network_bench_list(limit: int) -> None:
    """List saved network benchmarks."""
    from fpstune.benchmark.network import NetworkBenchmark

    nb = NetworkBenchmark()
    results = nb.list_results()

    if not results:
        console.print("No saved benchmarks found")
        console.print("\nRun 'fpstune network-bench run' to start benchmarking")
        return

    table = Table(title="Network Latency Benchmarks")
    table.add_column("Name", style="cyan")
    table.add_column("Target")
    table.add_column("Ping Avg", style="green")
    table.add_column("TCP Avg", style="yellow")
    table.add_column("Jitter", style="dim")
    table.add_column("Date")

    for path in results[:limit]:
        result = nb.load_result(path)
        if result:
            table.add_row(
                result.name,
                result.target,
                f"{result.stats.ping_avg:.1f} ms",
                f"{result.stats.tcp_avg:.1f} ms" if result.stats.tcp_count > 0 else "-",
                f"{result.stats.jitter_avg:.1f} ms",
                result.timestamp[:10] if result.timestamp else "",
            )

    console.print(table)


@network_bench.command("targets")
def network_bench_targets() -> None:
    """Show available test targets."""
    from fpstune.benchmark.network import NetworkBenchmark

    nb = NetworkBenchmark()
    targets = nb.get_available_targets()

    table = Table(title="Available Network Test Targets")
    table.add_column("Name", style="cyan")
    table.add_column("Host")
    table.add_column("Port")
    table.add_column("Description")

    descriptions = {
        "google_dns": "Google Public DNS",
        "cloudflare": "Cloudflare DNS",
        "steam": "Steam gaming platform",
        "riot": "Riot Games (LoL, Valorant)",
        "epic": "Epic Games Store",
    }

    for name, (host, port) in targets.items():
        table.add_row(name, host, str(port), descriptions.get(name, ""))

    console.print(table)


# ============================================================================
# dpc-bench command group
# ============================================================================


@click.group("dpc-bench")
def dpc_bench() -> None:
    """DPC latency benchmarking.

    Measure timer resolution and system responsiveness.
    Use this to evaluate timer tweaks (HPET, dynamic tick, resolution).
    """
    pass


@dpc_bench.command("run")
@click.option("--name", "-n", default="benchmark", help="Name for this benchmark")
@click.option("--samples", "-s", default=100, type=int, help="Number of samples")
def dpc_bench_run(name: str, samples: int) -> None:
    """Run a DPC latency benchmark."""
    from fpstune.benchmark.dpc import DpcBenchmark

    db = DpcBenchmark()

    console.print(f"\n[bold]Running DPC Latency Benchmark: {name}[/]")
    console.print(f"  Samples: {samples}")
    console.print("")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Measuring timer latency...", total=100)

        def update_progress(pct: int) -> None:
            progress.update(task, completed=pct)

        result = db.run_benchmark(
            name=name,
            sleep_samples=samples,
            jitter_samples=samples,
            progress_callback=update_progress,
        )

    if not result:
        console.print("[red]\u2717[/] Benchmark failed")
        return

    # Save result
    saved_path = db.save_result(result)
    console.print(f"[green]\u2713[/] Benchmark saved: {saved_path}")

    # Display results
    display_dpc_result(result)


@dpc_bench.command("resolution")
def dpc_bench_resolution() -> None:
    """Show current timer resolution."""
    from fpstune.benchmark.dpc import DpcBenchmark

    db = DpcBenchmark()
    res = db.get_current_resolution()

    table = Table(title="Timer Resolution")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row(
        "Current Resolution", f"{res['current_ms']:.4f} ms ({res['current_ms'] * 1000:.2f} us)"
    )
    table.add_row(
        "Minimum (Best)", f"{res['maximum_ms']:.4f} ms ({res['maximum_ms'] * 1000:.2f} us)"
    )
    table.add_row(
        "Maximum (Worst)", f"{res['minimum_ms']:.4f} ms ({res['minimum_ms'] * 1000:.2f} us)"
    )

    console.print(table)

    # Interpretation
    current = res["current_ms"]
    if current <= 0.5:
        console.print("\n[green]Excellent![/] Timer resolution is optimal for gaming (0.5ms)")
    elif current <= 1.0:
        console.print("\n[green]Good[/] Timer resolution is acceptable")
    elif current <= 10.0:
        console.print("\n[yellow]Suboptimal[/] Consider enabling timer resolution tweaks")
    else:
        console.print("\n[red]Poor[/] Timer resolution is too high, apply timer optimizations")


@dpc_bench.command("compare")
@click.option("--before", "-b", required=True, help="Before benchmark name or file")
@click.option("--after", "-a", required=True, help="After benchmark name or file")
def dpc_bench_compare(before: str, after: str) -> None:
    """Compare before/after DPC benchmarks."""
    from fpstune.benchmark.dpc import DpcBenchmark

    db = DpcBenchmark()

    before_result = load_dpc_result(db, before)
    after_result = load_dpc_result(db, after)

    if not before_result:
        console.print(f"[red]\u2717[/] Could not load 'before' benchmark: {before}")
        return

    if not after_result:
        console.print(f"[red]\u2717[/] Could not load 'after' benchmark: {after}")
        return

    comparison = db.compare(before_result, after_result)
    console.print(comparison.format_report())


@dpc_bench.command("list")
@click.option("--limit", "-l", default=10, help="Number of results to show")
def dpc_bench_list(limit: int) -> None:
    """List saved DPC benchmarks."""
    from fpstune.benchmark.dpc import DpcBenchmark

    db = DpcBenchmark()
    results = db.list_results()

    if not results:
        console.print("No saved benchmarks found")
        console.print("\nRun 'fpstune dpc-bench run' to start benchmarking")
        return

    table = Table(title="DPC Latency Benchmarks")
    table.add_column("Name", style="cyan")
    table.add_column("Resolution", style="green")
    table.add_column("Sleep Acc", style="yellow")
    table.add_column("Jitter", style="dim")
    table.add_column("Date")

    for path in results[:limit]:
        result = db.load_result(path)
        if result:
            table.add_row(
                result.name,
                f"{result.stats.timer_resolution_ms:.3f} ms",
                f"{result.stats.sleep_accuracy_avg_us:.1f} us",
                f"{result.stats.timing_jitter_avg_us:.1f} us",
                result.timestamp[:10] if result.timestamp else "",
            )

    console.print(table)
