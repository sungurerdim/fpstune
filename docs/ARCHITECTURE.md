# fpstune Architecture

This document maps the moving parts that ship together in fpstune: the FastAPI
backend, the React UI, the settings engine, and the system integrations they
talk to. It targets contributors who need a mental model before touching
code.

## High-level data flow

```
User clicks "Apply" in the React UI
    |
    | (Zustand action -> apiClient.applySetting)
    v
POST /api/settings/{id}/apply  (FastAPI route)
    |
    | (CommandExecutor.apply orchestrates)
    v
SettingExecutor.apply_type dispatches:
    REGISTRY  -> winreg via settings/executors/registry.py
    POWERCFG  -> subprocess powercfg
    NETSH     -> subprocess netsh
    BCDEDIT   -> subprocess bcdedit
    POWERSHELL-> run_powershell()
    NVPROFILE -> nvidiaProfileInspector wrapper
    |
    v
DetectionEngine re-runs detect_command to verify
    |
    v
JSON response -> React Query refetch -> UI refresh
```

## Backend (`src/fpstune/`)

### `api/` — HTTP surface

- `main.py` — FastAPI app factory, lifespan, CORS, static UI mount, /health
- `routes/settings.py` — list / detect / apply / reset / undo / verify
- `routes/settings_stream.py` — the SSE bulk apply and bulk reset
- `routes/system.py` plus `system_network.py`, `system_audio.py`,
  `system_power.py`, `system_common.py` — hardware info, split by subsystem
- `routes/display.py` — monitor detection + configuration
- `routes/gpu.py` — GPU profile detection and vendor apply endpoints
- `routes/safety.py` — restore-point endpoints
- `routes/benchmark.py`, `routes/benchmark_suite.py` — PresentMon captures, the
  measurement suite, claim verification and the headroom endpoints. (The FPS
  capture and GPU stress *commands* live in the CLI, `commands/benchmark.py` —
  there are no `fps.py` or `gpubench.py` route modules.)
- `routes/debug.py` — diagnostic endpoints, gated on `FPSTUNE_DEBUG=1`
- `schemas.py` — Pydantic v2 request/response models
- `status_cache.py` — module-level cache + background refresh thread
- `hardware/` — `network_adapters.py`, `storage.py`, `audio.py`: the read-only
  probes behind the hardware panel. They sit under `api/` rather than `utils/`
  because they return `api.schemas` objects, and outside `routes/` because none
  of them declares a router.

### `settings/` — Settings engine

- `base.py` — `SettingExecutor` dataclass (id, category, detect/apply
  command templates, value maps, applicability, risk and evidence level)
- `definitions/` — the static `SettingExecutor` instances split by category
  file (audio, display, game, gpu, launchers, network, power, priority,
  storage, system, timer, visual, game_configs, game_configs_mw4). The
  README states the count and a test holds it to the registry's own.
- `executors/` — one module per apply mechanism: `registry.py`, `powercfg.py`,
  `netsh.py`, `bcdedit.py`, `powershell.py`, `powershell_actions.py`,
  `ps_batch.py`, `nvprofile.py`, `nvidia_app.py`, `mw4_config.py`,
  `game_config_cache.py`, `game_processes.py`, `config_sweep.py`
- `detection.py` — `DetectionEngine` runs detection in parallel via
  `ThreadPoolExecutor`; honors per-setting `detect_timeout` overrides.
- `applicability.py` — `values_equal()`, the `ABSENT_READINGS` sentinel set,
  and `HardwareContext` filtering (GPU vendor, Windows build, form factor).
- `hardware_context.py` — the one builder, used by the API and the CLI alike.
- `registry.py` — `SettingsRegistry`: it stores settings and looks them up, and
  it runs the discovery passes in order. It does not contain them.
- `discovery/` — one module per discoverer (`probes.py`, `network.py`,
  `games_mw3.py`, `games_mw4.py`, `games_hots.py`, `display.py`,
  `headroom.py`). A discoverer is handed the `Registrar` protocol declared in
  `discovery/__init__.py` — `register`, `get`, `get_all` and nothing else — so
  it cannot reach into the registry's dict. The order in `all_discoverers()` is
  load-bearing (a pass that re-values a setting must run after the pass that
  registered it) and each entry says why. Adding a game is a new module plus one
  line there.
- `panel.py` — the one primary-panel derivation: which monitor is primary, and
  the highest rate it reports. Five call sites derived it independently, and a
  frame cap built from one reading against a target built from another are two
  answers to one question. An unknown rate stays 0 and never becomes 60.
- `groups.py` — which heading a setting renders under (its game, its kind of
  cleanup), so no screen has to spell a game's name itself.
- `performance_headroom.py` and `headroom_policy.py` — what a game measured
  against what the panel can show, and what that band and bottleneck are
  allowed to change.
- `impact_categories.py` — metric key to kind of gain.

### `core/` — System integrations

- `bcdedit.py` — Boot Configuration Database
- `power_profile.py` — powercfg wrapper, named-plan management
- `dism.py` — DISM component cleanup, AnalyzeComponentStore
- `nvapi.py` — NVAPI queries that do not need the inspector
- `nv_profile.py` — Downloads nvidiaProfileInspector, generates XML profile,
  invokes the binary. (Largest single class — split still open, see
  `docs/REFACTOR_PLAN.md`.)

### `safety/` — Reversible state

- `originals.py` — the first value this machine was seen holding, per setting
  (`~/.fpstune/originals.json`). Recorded by the full scan only, first write
  wins, and it is what `undo` writes back — a different promise from `reset`,
  which writes the curated stock value. The two must never collapse into one.
- `restore.py` — Windows System Restore Point (PowerShell + WMIC paths)

### `benchmark/` — what this machine actually did

Everything a user is shown as a *result* comes from here. `impact_scores` is
what a setting claims, and claims never add up to a measurement (gate C11).

- `suite.py` — the `Bench` protocol and the `BenchReading`/`BenchResult`
  shapes; a bench that cannot run returns `ran=False` with a readable reason
- `benches.py` — which benches exist, and which a "run everything" button may
  start
- `frame_pacing.py`, `disk_io.py`, `memory.py`, `timing_bench.py`,
  `network_bench.py`, `network_load.py` — the instruments themselves
- `presentmon.py` — PresentMon process management, CSV parsing, persistence
- `furmark.py` — stress orchestration, deliberately off the performance path
- `dpc.py`, `network.py` — DPC/ISR and latency/jitter analysis
- `verify_round.py` — `judge(claim, measurement)` over a computed noise floor
- `sources.py` — which claim metrics each instrument can measure, and a named
  reason for every one that nothing can
- `headroom_watch.py` — decides *when* to measure: once per game session
- `compare.py`, `runner.py` — before/after deltas and the high-level runner

### `commands/` — the CLI surface

One module per command family, shared vocabulary in `presentation.py`:
`status.py`, `gpu.py`, `scan.py` (the one detection pass both of those shape),
`benchmark.py` (the `fps`, `gpu-bench`, `network-bench` and `dpc-bench` trees),
`cleanup.py`, and `utils.py`. The CLI reports and measures; applying settings
stays on the API path so every write is verified.

### `diagnostics/` — one-question probes

Small measurements that exist to settle a specific argument rather than to run
in the suite: `mpo_effect.py` (what Multiplane Overlay actually changes here)
and `packet_burst.py`. They have their own test directory
(`tests/test_diagnostics/`).

### `resources/` — pinned facts shipped with the build

`checksums.json` — expected checksums for the external tools fpstune downloads,
so a fetched binary is verified rather than trusted.

### `utils/` — Cross-cutting helpers

- `detect.py` — GPU/CPU/monitor detection, in-process cache,
  background-thread detection (`start_gpu_detection_async`)
- `hardware_manager.py` — Singleton wrapping `detect.py` calls with
  request deduplication and TTL-based cache
- `admin.py` — `is_admin`, `require_admin` decorator, `elevate_if_needed`
- `powershell.py` — `run_powershell`, encoding-safe wrapper
- `logger.py` — Structured logging + activity log
- `console.py` — the one Rich Console the CLI and the logger both write through
- `config.py` — Path resolution (config dir, backups dir)
- `debug.py` — Debug-mode entry buffer
- `audio_format.py` — audio format parsing/formatting helpers
- `path_mtu.py` — path-MTU discovery for the network settings
- `runtime.py` — frozen-vs-source packaging facts (`sys._MEIPASS`, bundled UI)
- `updates.py` — release update check

## Frontend (`frontend/src/`)

- `App.tsx` — Top-level layout, tab routing
- `components/` — UI building blocks
  - `HomeTab`, `SettingsTab`, `HardwareTab`, `GameTweaksTab`,
    `DiskCleanupTab`, `BenchmarksTab` — one per tab
  - `TweakSetting`, `TweakRows`, `TweakListRow` — the settings list
  - `HardwarePanel` plus the `hardware/` package it composes (`MonitorCard`,
    `NetworkAdapterCard`, `StorageDriveCard`, `AudioSection`,
    `DeviceTweakList`)
  - `CleanupPanel`, `MaintenancePanel`, `SuitePanel`, `VerifyPanel`,
    `HeadroomPanel`
  - `ActionConsole`, `ActivityLog` — operation feedback
- `hooks/` — `useActionStream`, `useApplySingle`, `useBulkApply`,
  `useCleanupRunner`, `useImpactSummary`
- `lib/`
  - `api.ts` — typed client over the FastAPI surface (single file, split
    still open — `docs/REFACTOR_PLAN.md`)
  - `detection-manager.ts` — Coordinates detection requests, dedupes
    in-flight queries
  - `hardware-manager.ts` — Mirrors backend `HardwareManager`
  - `tweakDomain.ts` — the one place a tweak's domain is decided: predicates
    over the setting, never over `module`
  - `impact.ts` — per-row benefit text from `impact_scores`; claims only, and
    claims never add up to a headline
  - `logger.ts` — Structured logging
- `store/` — Zustand stores (settings, UI state)
- `types/` — Shared TypeScript types

## Process model

- One uvicorn process serves the API and (optionally) the built React UI
  via `StaticFiles` mount at `/ui`.
- A daemon thread runs GPU detection at startup
  (`start_gpu_detection_async`) so the first request doesn't block.
- `status_cache` runs an optional background-refresh thread that primes
  hardware info on a schedule. It is signalled to stop via
  `stop_background_refresh()` from the lifespan shutdown handler.
- Detection of multiple settings runs in a `ThreadPoolExecutor` so the
  event loop is never blocked by long subprocess calls.

## External dependencies

- Windows Registry (winreg) — settings r/w
- PowerShell — apply/detect for non-trivial settings
- powercfg.exe / netsh.exe / bcdedit.exe — subsystem CLIs
- DISM — cleanup operations
- nvidiaProfileInspector — fetched on first run, cached locally
- WMI / CIM — hardware queries
- PresentMon (bundled or downloaded) — FPS captures

## Quality gates (enforced — see CLAUDE.md)

1. Zero-risk tweaks
2. Numeric impact scores per setting
3. Tooltip text standardization
4. English-only strings
5. Stable hardware IDs (PNPDeviceID, UniqueId, InstanceId)
6. Apply/Reset/Verify correctness — reset and undo are different promises
7. Optimal caching per data type
8. Single-setting tweaks (no compound mutations)
9. Machine-neutral: nothing about the developer's machine or account
10. Vendor and platform complete: NVIDIA, AMD and Intel, or a named gap
11. Measured, or not claimed

## Toolchain

- Python: ruff + mypy strict, pytest + pytest-asyncio + pytest-cov
- Frontend: Vite + vitest, ESLint + TypeScript-ESLint, Tailwind
- Pre-commit: lefthook
- Build: PyInstaller via `fpstune.spec`
- Lock: uv (`uv.lock` is the source of truth; `requirements.txt` is generated)

## Known refactor backlog

See `docs/REFACTOR_PLAN.md` — it is in the repository, so a fresh clone has it.
Already landed from it: the `api/routes/system.py` split into per-subsystem
routers, the `executors/powershell.py` action-table extraction
(`powershell_actions.py`), and the `HardwarePanel.tsx` split into the
`components/hardware/` package. Still open: `core/nv_profile.py`,
`frontend/src/lib/api.ts`, and the large `definitions/` files.
