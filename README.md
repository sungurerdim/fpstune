# fpstune

Windows 11 Gaming Performance Optimization Tool

## Philosophy

| Criterion | Rule |
|-----------|------|
| **Zero-Risk** | All tweaks are safe, reversible, and tested on real hardware |
| **Frames First** | The minimum tier is the default answer; only information earns more |
| **Concrete Benefit** | Every setting has a measurable numeric impact score |
| **Measured, or Not Claimed** | A number you are shown was produced by an instrument on your machine |
| **Verified** | Apply → detect → verify cycle for every change |
| **English Only** | All strings in English; no locale-sensitive commands |

**Frames first, in full.** In a competitive game the frame rate is the point, so
the burden of proof runs the other way: every setting's default answer is its
lowest tier, and raising one has to be argued as *something the player reads*.
Enough visual detail to tell an opponent apart, enough audio to hear where a
sound came from — and not a tier above that, because everything above it is
spectacle and spectacle is what gets spent for frames.

Two things that are easy to get backwards. A quality tier is bought with frames,
so a machine that has not reached its own target has nothing to buy with; what
your games actually achieve is measured rather than assumed, and below target the
answer is the minimum tier that still carries the information. And minimum is not
zero — a preset that flattens spell effects buys frames and loses the fight, so
this rule raises a setting as readily as it lowers one.

**What we exclude:** placebo tweaks, kernel-mode drivers, Defender-disable, UAC-disable, firmware changes, registry hacks without benchmarks.

**What we include:** timer (HPET, dynamic tick, TSC sync), GPU vendor profiles (NVIDIA/AMD), power management, TCP/IP stack tuning, per-game config files.

---

## Tweaks Overview

**395 settings across 13 categories**, plus per-adapter network settings discovered from your own hardware at runtime. Every setting carries a `risk_level` (`safe` / `low` / `moderate` / `advanced`). Advanced tweaks are shown alongside the rest and surface an inline `risk_warning`.

| Category | Count | Highlights |
|----------|------:|------------|
| Game Configs | 174 | Per-game config file optimization (MW3, MW4, CS2, Heroes of the Storm) |
| System | 65 | Services, privacy, telemetry, scheduler |
| Maintenance | 38 | SFC, DISM, temp/cache cleanup |
| GPU | 30 | NVIDIA and AMD driver profile optimizations |
| Network | 28 | TCP/IP, DNS, QoS — plus per-adapter driver keywords |
| Power | 25 | CPU clock behaviour under load and at idle, core parking, USB suspend, disk timeout |
| Launchers | 12 | Steam, Battle.net overlay/GPU/shader settings |
| Core | 6 | Priority separation, system responsiveness, GPU priority |
| Game | 5 | Game Mode, Game Bar, HAGS |
| Audio | 5 | Audio enhancements, loudness EQ |
| Visual | 3 | Animations, transparency, smooth scrolling |
| Storage | 3 | NVMe, disk timeout, write caching |
| Timer | 1 | Timer resolution |

Counts are the static registry. On a real machine the network total is higher: each adapter contributes its own settings, and their choices come from that adapter's driver — a NIC that offers sixteen RSS queues is offered sixteen, not a number written into this repo.

---

## Installation

### Windows Executable

Prebuilt executables are published on the [Releases](https://github.com/sungurerdim/fpstune/releases) page. **There is no published release yet** — until the first tag lands, install from source.

Once a release exists, it is a single `.exe` with the UI bundled inside it. No
installer, no runtime to install, nothing written outside `%USERPROFILE%\.fpstune`.

#### Windows will warn you, and here is exactly why

SmartScreen shows *"Windows protected your PC"* for this executable. The reason
is mundane: the binary is **not code-signed**. A certificate that clears
SmartScreen immediately costs several hundred dollars a year, and since 2024
even an EV certificate no longer buys instant reputation — it accrues over
downloads. For an unfunded open-source tool the honest trade is to stay unsigned
and make the binary verifiable instead.

So verify it rather than trusting it:

```powershell
# 1. The hash of the file you downloaded
Get-FileHash .\fpstune.exe -Algorithm SHA256

# 2. Compare against fpstune.exe.sha256 on the same release page
```

Every release also carries a **GitHub build provenance attestation**, which is a
stronger claim than a hash: it says which commit, which workflow and which
runner produced that exact file. Check it with:

```bash
gh attestation verify fpstune.exe --repo sungurerdim/fpstune
```

That is not a signature and does not silence SmartScreen. It does mean nobody
can substitute a different binary for the one this repository built.

#### It will ask for Administrator

fpstune reads and writes registry keys under `HKLM`, power scheme values, and
network adapter driver properties. None of that is readable — let alone
writable — from a normal user token, so the executable requests elevation at
launch and Windows shows a UAC prompt.

Started without elevation, it relaunches itself elevated and the original window
exits. If you decline the prompt, nothing happens and nothing is changed.

### From Source

```bash
git clone https://github.com/sungurerdim/fpstune.git
cd fpstune
python scripts/dev_setup.py     # installs uv/pip deps + npm install
```

On a source checkout, `start.bat` (or `start.ps1`) does the same thing the
executable would: it self-elevates, then launches the UI in a new terminal.

---

## Quick Start

### Web UI

```bash
fpstune     # starts the backend and opens the browser
```

This is the path that applies settings, because it is the path that shows what
each change costs as well as what it gains, and verifies afterwards that the
change actually took effect.

Or manually, for development:
```bash
task serve          # FastAPI on :8000 (dev auto-reload)
task dev-frontend   # Vite on :5173 (separate terminal)
```

### CLI

The command line reports and measures; it does not apply. A second apply path
that skipped the verification step would be a way to believe a machine had been
tuned when it had not.

```bash
fpstune status       # what this machine is set to, and what is left to do
fpstune gpu          # how this GPU is configured, and what would change
fpstune benchmark    # measure this machine (--after to compare against a baseline)
fpstune cleanup      # free disk space
fpstune bios         # reboot straight into BIOS/UEFI setup (--cancel to abort)
fpstune serve        # start the web UI by hand (ports, --api-only, --no-browser)
fpstune update       # check whether a newer release exists
fpstune -v status    # any command, with the full log
```

Four commands are measurement trees of their own, each with `list` and
`compare` subcommands: `fpstune fps` (PresentMon capture — see below),
`fpstune gpu-bench` (FurMark stress), `fpstune network-bench` (latency and
jitter against named targets) and `fpstune dpc-bench` (DPC latency and timer
resolution). `--help` on any of them lists the rest of its tree.

---

## Development

### Tasks ([Taskfile](https://taskfile.dev/))

```bash
task                # list all tasks
task serve          # FastAPI dev server (auto-reload)
task dev-frontend   # Vite dev server
task test-fast      # pytest without coverage
task test-frontend  # vitest run
task lint           # ruff + mypy
task build          # PyInstaller exe
task lock           # regenerate uv.lock + requirements.txt
```

### Manual (no Taskfile)

```bash
pip install -e ".[dev]"
uvicorn fpstune.api.main:app --host 127.0.0.1 --port 8000
cd frontend && npm install && npm run dev
pytest tests/ -x --tb=short
ruff check src/
```

---

## Settings API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/settings/definitions` | GET | All setting definitions. Includes the per-adapter settings discovered from your hardware, so the registry is built once at startup in the background — the request itself is instant unless it beats that warm-up |
| `/api/settings/detect` | POST | Parallel detection of all settings (empty body) |
| `/api/settings/detect/{id}` | GET | Detect a single setting |
| `/api/settings/{id}/apply` | POST | Apply a value, detect, verify |
| `/api/settings/{id}/reset` | POST | Write the Windows stock `default_value`, detect, verify |
| `/api/settings/{id}/undo` | POST | Write what this machine held when fpstune first saw it; 409 if unrecorded |
| `/api/settings/{id}/verify` | POST | Detect only — `{matches, current_value, expected_value, target}`; `target` picks `recommended` (default), `default`, or `original` |
| `/api/settings/bulk/apply` | POST | Parallel bulk apply of a `{id: value}` map |
| `/api/settings/bulk/reset` | POST | Parallel bulk reset to `default_value` |
| `/api/settings/bulk/optimize` | POST | Parallel bulk apply of `recommended_value` |
| `/api/settings/bulk/stream-apply` | POST | Sequential SSE bulk apply (per-setting events) |
| `/api/settings/bulk/stream-reset` | POST | Sequential SSE bulk reset (per-setting events) |

The `/revert` endpoint is deprecated; use `/reset`.

The settings surface is the largest, not the whole API. The other groups, all
under `/api`, exist so the UI never has to shell out for anything:

| Surface | What it covers |
|---------|----------------|
| Display | `/display/monitors`, `/display/refresh`, `/display/{index}/auto`, and `/display/vrr-optimization` (read, apply, reset) |
| GPU | `/gpu`, `/gpu/detect`, `/gpu/settings`, `/gpu/apply` plus the vendor-specific `/gpu/nvidia/apply` and `/gpu/amd/apply` |
| Power profile | `/power-profile/status`, `/power-profile/activate`, `/power-profile/revert` |
| Network | `/network/refresh`, plus per-adapter enable/disable, connection toggle, and `/network/adapter/{name}/status` |
| Audio | `/audio/refresh`, per-device enable/disable, and per-device loudness EQ |
| Hardware and status | `/system`, `/hardware`, `/hardware/context`, `/status`, `/activity` |
| Safety | `/restore-point` — create and list System Restore points |
| Elevation | `/elevate` — relaunch the backend with Administrator rights |

Debug endpoints exist too, but only when the process runs with `FPSTUNE_DEBUG=1`.

---

## Did it actually do anything?

Every setting carries an `impact_scores` claim — `{"fps": "+3-5%"}`,
`{"latency_ms": -15.0}`. None of those numbers came from *your* machine. They
came from vendor documentation, community benchmarks, somebody else's hardware.

So there is an engine that compares them to yours, and most of its rules exist
to stop it flattering itself:

- **A shared measurement is not per-setting evidence.** Apply forty settings,
  measure once, and you have learned what forty settings did together. Splitting
  that credit forty ways would be inventing data, so a round knows how many
  settings changed and only a one-setting round produces per-setting verdicts.
- **Noise is not a result.** Two runs of the same measurement on an idle machine
  differ. Every round measures its own noise first and refuses to call anything
  smaller than that a change.
- **"Not checked" is never reported as "no effect."** A frame-rate claim cannot
  be checked without a game running. That is a limit of the measurement, not a
  fact about the setting.
- **A sum of claims is not a measurement.** Adding every setting's claimed gain
  together produces a headline number no instrument could ever confirm. It has
  been shipped here three times and removed three times; it is now a rule.

### The instrument is fixed, the load varies

[PresentMon](https://github.com/GameTechDev/PresentMon) measures anything that
renders — any vendor, D3D9/11/12, OpenGL, Vulkan — so whatever we put in front
of it (your game, or a scene fpstune draws itself) comes back in the same
vocabulary: frame time, CPU busy, GPU time, GPU wait, input-to-photon latency.
That is what makes "max settings here, low settings there" one comparison on one
axis instead of two unrelated scores.

The corollary is that a stress test is not a performance test. FurMark answers
"how hot, how stable"; it does not answer "what does this machine reach", so it
sits on its own panel and stays off the performance path.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/benchmark/verify/coverage` | POST | Which of these settings' claims are measurable here, which are not, and why — answered *before* anything runs |
| `/api/benchmark/verify/sources` | GET | The instruments themselves: what each can measure, and what each requires |
| `/api/benchmark/verify/sample` | POST | Take one measurement sample now, for a before/after pair |
| `/api/benchmark/verify/round` | POST | Judge a before/after pair and return the verdict — nothing is written to disk |
| `/api/benchmark/headroom` | GET | What each known game last reached on this machine, against what the display could show |
| `/api/benchmark/headroom/measure` | POST | Measure now, on a game that is running |
| `/api/benchmark/suite` | GET | Which benches exist, which can run here, what each costs, and why the rest cannot |
| `/api/benchmark/suite/run` | POST | Run them, streaming one event per bench (SSE) |
| `/api/benchmark/suite/compare` | POST | Judge two runs metric by metric — nothing is stored |

The PresentMon capture flow has its own endpoints as well —
`/api/benchmark/start`, `/status`, `/baseline`, `/results` and `/compare` —
which is what the `fpstune fps` commands and the in-game measurement use.

The suite is six instruments, and none of them needs a game running:

| Bench | Measures |
|-------|----------|
| Frame pacing | Whether the machine holds a cadence — interval, p99, p999, jitter, missed frames |
| Timer and scheduling | Timer resolution, sleep accuracy, timing jitter |
| Memory | Bandwidth, and dependent-load latency |
| Disk | Sequential MB/s, 4K random IOPS and p99 latency, past the file cache |
| Latency on an idle line | Round trip and jitter with nothing else on the line — the baseline the loaded number is judged against |
| Throughput and load | Download rate, and what the round trip does while the line is busy |

The last two are separate entries on purpose: latency at idle and latency under
load answer different questions, and `GET /api/benchmark/suite` returns them
separately.

"Run everything" does not mean every bench. The throughput one downloads about
25 MB, so it runs when you name it — a button that spends your data because you
pressed the broad one is a button that gets pressed once.

Coverage over the shipped registry today: **324 of 664 claims are measurable**
(151 via network latency, 151 via PresentMon, 11 via FurMark, 6 via timer
jitter, 3 via disk I/O, 1 via memory bandwidth, 1 via throughput). The other
340 are listed with a reason rather than dropped, and they are not one pile.
109 are not the kind of claim an instrument settles at all — privacy, whether
a footstep is audible — and filing those as gaps would invent a to-do list
nothing can ever close. The real shortfall is 231: 198 name the instrument
this build lacks (68 need a GPU/CPU-bound split, 35 a CPU-time sampler, 29 a
memory or VRAM sampler), 23 state no number at all, and 10 state a ceiling
that cannot be scored as a gain in either direction.

That second number is the point. A tool reporting "4 of 4 claims verified" after
silently discarding fifty-six is saying something false with true arithmetic.

---

## Safety

1. **System Restore Points** — created before any operation that writes: apply, reset and undo alike
2. **Verify after Apply** — every apply is followed by detection to confirm the change took effect, so a write that silently failed is reported rather than assumed
3. **Two different ways back**, because they are different promises:
   - **Restore the Windows default** — writes the curated stock value
   - **Undo fpstune's change** — writes what *your* machine held when fpstune first saw the setting. On a machine that deliberately ran something non-stock, a reset would discard that choice; this does not.
4. **Protected Services** — critical services cannot be disabled
5. **Applicability checks** — NVIDIA tweaks hidden on AMD systems; a setting whose feature is absent from your hardware is not offered at all
6. **Advanced tweaks** show alongside the rest with an inline `risk_warning` badge

Originals are recorded by the first scan that reads a setting, and never
overwritten, so they survive restarts. The honest limit: if you tweaked a setting
with an earlier fpstune release and only then ran this one, what it recorded is
the already-tweaked value — it remembers what it saw, not what was true before
anything ever ran. Undo is offered only where there is a recorded original that
differs from the current value.

There is no file-level backup manifest — earlier versions of this README
described one, and it was never implemented.

---

## FPS Benchmarking

fpstune integrates [PresentMon](https://github.com/GameTechDev/PresentMon) for real-game FPS capture:

```bash
fpstune fps install                        # auto-download PresentMon
fpstune fps start --game "game.exe"        # start capture
fpstune fps stop --name "before"           # save session
fpstune fps list                           # saved sessions
fpstune fps analyze                        # metrics for one session
fpstune fps compare --before b --after a   # before/after diff
```

Metrics: avg FPS, 1% low, 0.1% low, frame time std-dev, stutter count.

---

## Architecture

```
src/fpstune/
  api/              FastAPI backend
    routes/         settings.py + settings_stream.py (apply/reset/undo/verify, SSE bulk),
                    system*.py, display.py, gpu.py, benchmark*.py, safety.py, debug.py
  settings/         Settings engine
    definitions/    14 category files producing the 395 settings in 13 categories —
                    the file count and category count differ because the game-config
                    files generate most of their settings from per-game tables
                    rather than writing each out as a literal
    executors/      Registry, PowerShell, Netsh, POWERCFG, NvProfile, game config writers
    detection.py    Parallel detection (ThreadPoolExecutor)
    applicability.py  HardwareContext filtering + values_equal()
    base.py         SettingExecutor schema (risk_level, evidence_level, impact_scores)
  core/             BcdEdit, DISM, NV Inspector, power profiles
  safety/           System Restore points + per-machine originals (what undo writes back)
  benchmark/        PresentMon, FurMark, DPC latency, the suite, claim verification
  commands/         the CLI surface (status, gpu, benchmark, fps, cleanup, ...)
  diagnostics/      one-question probes (MPO effect, packet burst)
  utils/            Hardware detection, admin check, logging, PowerShell runner

frontend/src/       React + Vite + TypeScript + Tailwind
  components/       SettingsTab, GameTweaksTab, TweakSetting/TweakRows,
                    SelectionToolbar (SSE bulk), HardwarePanel + hardware/ cards,
                    CleanupPanel, SuitePanel, VerifyPanel, HeadroomPanel
  store/            Zustand (settings state + selection)
  lib/              API client, detection manager, tweakDomain predicates
```

**Data flow:** React UI → `POST /api/settings/{id}/apply` → `CommandExecutor.apply()` → PowerShell/registry → `_finalize_apply_response()` → detect+verify → Zustand update → UI refresh.

**Bulk SSE flow:** SelectionToolbar → `bulkStreamApply/Reset` → `/bulk/stream-{apply,reset}` → per-setting `asyncio.to_thread` → streamed events → row status badges.

---

## Requirements

- **Windows 11** (21H2+) — primary target, fully tested
- Windows 10 (1903+) — basic compatibility
- Administrator privileges required
- Python 3.12+ (source installation only). The floor is the oldest version CI
  actually runs, never a wider range nobody executes: every push runs the whole
  backend suite on 3.12 and on 3.13, and the released exe is built on 3.12

---

## Building

```bash
pip install -e ".[dev]"         # PyInstaller is already a locked dev dependency
python scripts/build_exe.py     # single-file Windows exe (expects frontend/dist to exist)
python scripts/build_all.py     # frontend build + tests + exe + staged release folder
```

---

## License

MIT — see LICENSE.

## Disclaimer

This software modifies Windows system settings. All changes are reversible. Use at your own risk and always verify with a system restore point.
