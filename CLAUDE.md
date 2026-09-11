# FPSTune Project Rules

## Product Goal

Tune every point of a Windows 11 machine to the ceiling of *that* hardware and
*that* internet line. Not a preset, not a generic checklist. Six consequences:

1. **Derive from the hardware, never assume.** The right value is what the device
   reports: the panel's own max refresh, the adapter's `ValidRegistryValues`, the
   driver's own keyword spelling, the NIC's `NumericParameterMaxValue`. A hardcoded
   constant is a bug waiting for hardware that disagrees — `1024` buffers (#45),
   `1Gbps_Full` on 2.5GbE, `*AdvancedEEE` on Realtek all shipped and all were wrong
   on real hardware.
2. **Leaving a default alone, and undoing, are legitimate answers.**
   `recommended_value == default_value` is a drift guard: it detects a change from
   another "optimizer", a guide or an earlier fpstune release and puts the machine
   back. Removing harm counts as much as adding tweaks.
3. **A tweak that can lower the ceiling is not a tweak** (C1 with teeth). Forcing
   link speed breaks auto-negotiation; a background frame cap can cap the
   foreground game. Both shipped; both cost more than they gained.
4. **Heat is a performance category, not a comfort one.** Thermal throttling decays
   frame rate in minute forty, not at the moment of the tweak. Anything that cuts
   heat or wear *without costing performance when it is wanted* is in scope: a menu
   frame cap, a 30 fps cap on an unfocused game, an idle core allowed to clock
   down. These go under the `thermal` impact category ("Heat & wear" in the UI),
   never `fps`. Mirror: `Minimum processor state = 100`, `Processor idle disable =
   1` and NVIDIA "Prefer maximum performance" buy zero frames and cost heat all
   session, so undoing them is a tweak (consequence 2).
5. **Frame rate is priority one; the minimum is the default answer, and only
   information earns more.** Applies to every setting, not only game config files.
   The default for anything that costs frames is its lowest tier; raising it is the
   exception and must be argued in the setting's own copy, which the player reads.
   Enough visual quality to tell an opponent apart, enough audio to hear where a
   sound came from and what it was — not one tier above.
   - **Spend only headroom you have measured.** `headroom_watch` measures what each game
     achieves against what the panel can show. Below target → the minimum tier that
     still carries the information; at target → the quality-leaning value. A
     frame-costing recommendation on a machine at 19% of its target is a
     regression, and must never sit in `recommended` scope.
   - **An information channel has its own minimum, and that minimum is the
     answer.** Ask *what is the lowest tier at which this still says what it says*,
     and stop there — a shadow at `Low` still gives a corner away.
   - **Minimum is not zero.** `SoundSampleRate=22050` in a shipped config is a
     functional loss, and raising it is a *tweak*. The rule cuts upward as often as
     down; it never leaves a setting high because the default was high, or because
     the channel matters.

   The line runs between **information and decoration**, not high and low:

   | Functional — keep, raise if lowered | Decorative — spend it |
   |---|---|
   | Model and texture detail on enemies | Bloom, depth of field, motion blur |
   | Ability and spell effects (a cast is *announced* by its particles) | Cloth, ragdoll, debris physics |
   | Audio sample rate and channel count (footstep direction is information) | Cinematics, 3D portraits, water reflections |
   | Anything that changes what the player can *see coming* | Ambient occlusion, shadow softness where shadows carry nothing |

   Scope follows the side: imperceptible cost → `ESSENTIAL`/`RECOMMENDED`; changes
   what the player sees or hears → `COMPLETE`, cost written in the copy, offered
   never assumed. Which side a setting lands on is decided **per game** — shadows
   are decoration in an isometric MOBA, information in a shooter where one is cast
   around a corner.

6. **Retiring a harmful tweak means guaranteeing its harmless value** (decided
   2026-09-02). Machines already carrying it keep carrying it, so deleting the row
   hides the harm. Two halves: the tweak leaves, and a guard arrives whose
   `recommended_value` is the harmless state, derived like every value (scheme
   default from `DefaultPowerSchemeValues`, the driver's own default, Windows
   stock) — a network-adapter keyword pulled for doing harm keeps its harmless
   value as fpstune's default. Mirror for proposals: an item dropped as "not a
   tweak" whose *active* state is the beneficial one ships as a recommendation
   instead of disappearing (Wi-Fi background-scan blocking on a good signal,
   transmit power at the driver's maximum). Two limits: no guards for no-ops (a
   placebo key Windows 11 ignores has no harmful state to undo), and no way back
   for tweaks whose harm was the point (a security-costing switch stays retired;
   its guard restores the mitigation).

## 11 Quality Gates — non-negotiable for every PR, feature, and setting

### C1 — Zero-Risk Tweaks
Every tweak safe on any compatible system. No crashes, BSODs, data loss, or app incompatibility.
- `evidence_level="experimental"` → `description`/`effect` must include explicit risk warning
- `risk_level="advanced"` → `risk_warning` must be non-None
- Advisory settings (BIOS, physical) → `is_readonly=True`

### C2 — Numeric Impact Scores
Every `SettingExecutor` has ≥1 numeric/range `impact_scores` entry.
Allowed: `{"fps": "+3-5%"}`, `{"latency_ms": -15.0}`, `{"ram_saved": "50-150MB"}`, `{"disk_freed": "4-16GB"}`
Forbidden: `impact_scores={}` or only `"stability": "high"` with no performance/resource metric.
Gate: `assert any(k != "stability" for k in setting.impact_scores)`

### C3 — Tooltip Text Format
- `description`: 1-2 complete sentences ending with `.` — `"[What it controls]. [Why it matters]."`
- `current_impact`: `"State: Brief consequence"`
- `recommended_impact`: `"State: Specific measurable benefit"`
- `effect`: short active-voice phrase, no trailing period
Forbidden: fragment descriptions, descriptions not ending with `.`

### C4 — English in code; the UI ships en + tr
Code, comments, identifiers, errors and docs in English. User-facing strings live in
`frontend/src/i18n/` with an English and a Turkish form; the Turkish catalogue is
typed against the English one, so locales cannot drift silently. Amendment F1
(2026-08-26): the product ships to Turkish users. Turkish is legal *only* inside
`frontend/src/i18n/`; anywhere else it is a C4 violation.

Carve-out (evidence, not language): a comment quoting what Windows *printed back*
keeps the quote verbatim. `ping.exe`, `ValidDisplayValues` and `netsh wlan show interfaces` answer in the
system language, and those quoted strings are the reason each code path reads a
numeric enum (WiFi: wlanapi.dll's own numbers), not text.

Gate: `tests/test_quality_gates.py::TestC4EnglishOnly` — compares characters, holds
the carve-out to the exact quoted phrases. By hand (the old shell form matched byte
by byte under Git Bash and read `✓`, `°`, `±` as Turkish letters):
`LC_ALL=C.UTF-8 grep -rnP "[çğıİöşüÇĞÖŞÜ]" --include=*.py --include=*.ts --include=*.tsx src/ frontend/src/`

### C5 — Stable Hardware IDs
Use immutable, order-independent identifiers:
| Hardware | Required ID |
|---|---|
| GPU | `PNPDeviceID` (VEN+DEV) or vendor name |
| Storage | `UniqueId` (EUI-64/serial) from `Get-PhysicalDisk` |
| Network | `InstanceId` (PnpDevice `PCI\VEN_...`) |
| Monitor | WMI `DeviceID` or `EnumDisplayDevices` UID |
Exception: `InterfaceIndex` OK for netsh commands (command-only, not ID storage).

### C6 — Apply/Reset/Verify Correctness
- `_verify_setting_applied()` uses `values_equal()` from `applicability.py` (strip/CRLF/cross-type coercion)
- Post-apply detect+verify+log consolidated in `_finalize_apply_response()` — never duplicate
- Bulk ops use `asyncio.to_thread()` (never bare `asyncio.gather()` over sync subprocess)
- Detection never returns a value outside the `choices` tuple; `value_map` covers all raw outputs

Single-setting endpoints:
- `POST /settings/{id}/apply` — apply, detect, verify
- `POST /settings/{id}/reset` — write `default_value` (Windows stock), detect, verify
- `POST /settings/{id}/undo` — write the recorded original, detect, verify, then forget it;
  409 when nothing was recorded (never falls back to reset)
- `POST /settings/{id}/verify` — detect only → `VerifyResponse{matches, current_value, expected_value, target}`;
  `target` ∈ `recommended` (default) | `default` | `original` names which question was asked
- `POST /settings/bulk/stream-{apply,reset}` — sequential SSE, events started/applied/verified/failed/done

Reset and undo are different promises and must never collapse into one: reset writes
the curated stock value, undo writes what this machine held; they agree only on a
machine that was stock to begin with. Originals are recorded by the **full scan**
(`POST /settings/detect`) and never by a single re-detect, which runs after an apply
and would capture fpstune's own write. First write wins; `safety/originals.py`
persists to `~/.fpstune/originals.json`.

### C7 — Optimal Caching
| Data | Cache | TTL |
|---|---|---|
| GPU info | `detect.py` module cache | ∞ |
| OS info | `hardware_manager` | ∞ |
| Monitor info | `hardware_manager` | 5 min (hot-reload 15s poll) |
| Settings registry | `_registry` module-level | ∞ |
| Frontend static | React Query `staleTime: Infinity` | ∞ |
| Frontend dynamic | React Query `staleTime: 5000` | 5s |
Forbidden: subprocess/PowerShell on every request for session-stable data.

### C8 — Single-Setting Tweaks
Each `SettingExecutor` changes exactly 1 logical setting. Named-compound exceptions
(1 concept, keep together): mouse acceleration = 3 registry values; DNS = primary +
secondary IP; telemetry = 9 tasks + 1 registry key; DSCP QoS = NLA flag +
NetQosPolicy entries; browser cache cleanup = Edge/Chrome/Brave/Firefox.

Forbidden: bundling unrelated subsystems (e.g. `WaitToKillServiceTimeout` + `HungAppTimeout` + `AutoEndTasks`).
Split example: `system:network_afd_receive_window` + `system:network_afd_send_window`.
Gate: no `ACTION_COMMANDS` entry bundles >1 logical subsystem unless named-compound.

### C9 — Machine-Neutral: nothing about the developer's machine or account

C1 derives values from the hardware; C9 says the same about **where things live and
who owns them**. Every path, identifier and name a tweak touches is discovered at
runtime, never carried in the source: the product must behave identically on a
machine fpstune has never seen, under an account it has never heard of. Forbidden in
source, tests and fixtures — any literal that exists only because of the machine it
was written on:

| Class | Never hardcode | Discover instead |
|---|---|---|
| User & account | username, `C:\Users\<name>`, account/profile IDs (MW4's `playersBeta\<account id>`) | `%LOCALAPPDATA%` + glob the profile dir |
| Install location | `D:\<user-named library>\...`, any drive letter or library path | Steam/Battle.net/Epic registry + library folders |
| Build-tagged paths | `playersBeta`, `bt.cod26` — beta names that change at release | glob the pattern, take newest match |
| Display | monitor model, resolution, refresh rate | EDID/WMI, panel's own max |
| GPU/CPU | model string, VRAM, thread count, driver version | `detect.py`, `hardware_context` |
| Config key suffixes | MW4's `@0;14317;21371` hashes | read the line, keep the suffix verbatim |

Two rules follow:

1. **Match on the stable part, preserve the volatile part.** For MW4 the key is
   `Name@<scopeIndex>`: the scope index disambiguates (`DxrMode@0` is Off/On,
   `DxrMode@1` is Off..Ultra) while trailing hashes are copied through untouched.
   Never reconstruct a key you did not read.
2. **A file's own metadata beats a constant.** MW4 ships `// 0 to 3` and
   `// one of Low, High` on every line; those are the range and the `choices`.

Gate: `tests/test_quality_gates.py::TestC9MachineNeutral`, over executable lines of
shipped source only. Two deliberate exclusions: these literals are legitimate in a
comment documenting *why* a code path exists, and in a test as fixture input. By hand
(each scrubbed literal spelled as a character class so this document never contains
it — the history scrub requires zero tree-wide hits; `grep -E` reads both spellings
identically):

```bash
grep -rnE "(Q25G4[S]|41613607[3]|Oyunla[r]|RTX 307[0]|i7-11800[H]|Users\\\\[A-Za-z])" \
  --include="*.py" --include="*.ts" --include="*.tsx" \
  --exclude-dir=__pycache__ --exclude-dir=__tests__ \
  --exclude="*.test.ts" --exclude="*.test.tsx" \
  src/ frontend/src/ | grep -vE ":[0-9]+:[[:space:]]*(#|//)"
```

### C10 — Vendor & Platform Complete

Every setting must be correct on all three GPU vendors, on any CPU, and on every
Windows 11 edition — where "correct" includes *knowing it does not apply*.

- **Symmetry.** A vendor-specific concept ships for all vendors or is named as a gap:
  upscaling = DLSS + FSR + XeSS; low-latency = Reflex + Anti-Lag 2 + XeLL; frame
  generation = DLSS-FG + FSR-FI + XeSS-FG. Shipping only the NVIDIA half leaves AMD
  and Intel users a measurably worse ceiling.
- **Not-applicable is a first-class answer.** A setting that cannot apply reports an
  `ABSENT_READINGS` sentinel → `is_applicable=False`. Never write a value the hardware
  will reject; never show a control that does nothing.
- **CPU/GPU capability, not model lists.** Thread counts, core counts, VRAM, P/E-core
  split and `mobile` come from detection; a model-name allowlist is the same bug as a
  hardcoded constant.
- **Editions and form factors.** Home lacks BitLocker cmdlets; laptops have a battery
  and a thermal ceiling desktops do not; a 60 Hz and a 500 Hz panel derive different
  caps from the same rule.

Gate: for every vendor-specific setting, either a sibling exists for the other two
vendors or `tasks.md` records the gap with a reason.

### C11 — Measured, or Not Claimed

Every number a user is shown was produced by an instrument on *that* machine, or it is
not shown; "derived from what the settings claim" is not a third option. Three
meaningless headlines shipped and must never return: `"GAINED -683ms LATENCY"` (DNS
lookup, mouse polling, timer resolution and NIC buffering are different clocks over
different events, so the sum has no referent — `impact.ts`, `latencyTweaks`),
`dns_security`'s unmeasured `-12 ms`, and `"Gained +28-45% FPS"` (claimed fps midpoints
summed under an invented decay curve). Seven rules:

1. **A sum of claims is not a measurement.** Adding `impact_scores` up and showing the
   total is forbidden anywhere a user can see it. `impact_scores` is what a setting
   *claims*; only `benchmark/` produces what a machine *did*.
2. **A measurement is a list of samples, not a number.** A difference whose noise
   floor could not be computed is not a difference. `verify_round.measure_pair()` over
   `noise_floor()` is the one comparison path — a single reading yields infinite noise
   and therefore no verdict, deliberately.
3. **What could not be measured says so.** A bench never drops out quietly: it returns
   `ran=False` with a `reason` a user can read (`sources.py`'s "here is why we cannot
   check that", across the whole measurement surface).
4. **A qualitative claim is not a missing instrument.** `privacy`,
   `target_visibility`, `footstep_clarity`, `ux`, `security` are real claims no
   benchmark adjudicates — their own class of unmeasurable, never filed under "states
   no number" or "no instrument", which would invent an unclosable to-do.
5. **Every area we improve gets an instrument, or the gap is on the record.** Every
   impact metric a shipped setting claims has a source in `SOURCES` or a named reason
   in `NO_INSTRUMENT`. No silent third state.
6. **A stress test is not a performance test.** FurMark is a power virus: it answers
   "how hot, how stable", never "what does this machine reach". It stays off the
   performance path and keeps its own panel.
7. **A vendor-neutral instrument beats a vendor's wrapper.** C10 applied to tool
   choice: PresentMon reads all three vendors, so FrameView — board power on NVIDIA,
   chip power only on AMD — would be a regression.

The load may vary (a real game, our own scene); the instrument does not. That keeps
"max settings here, low settings there" one comparison on one axis.

Bindings, because a rule nothing enforces is decoration:

| Rule | Bound by |
|---|---|
| 1 | `tests/test_quality_gates.py` (this gate's own paths resolve) + the red-proven test landing with the headline rewrite |
| 2 | `tests/test_benchmark/test_verify_round.py` |
| 3 | `tests/test_benchmark/test_sources.py` |
| 4, 5 | `NO_INSTRUMENT` in `src/fpstune/benchmark/sources.py` + its tests |
| 6, 7 | the composition of `SOURCES` in `src/fpstune/benchmark/sources.py` |

A clause with no binding yet names, in `tasks.md`, the step that gives it one — the
same escape hatch C10 uses. A clause that can never be bound is not written.

---

## Risk Taxonomy

Every `SettingExecutor` carries `risk_level`. All tweaks (including `advanced`) are
shown; `advanced` settings surface their `risk_warning` inline in the UI.

| Level | Meaning | `risk_warning` |
|---|---|---|
| `safe` | No side-effects, proven all hardware | not required |
| `low` | Default; well-understood, rare edge-case | not required |
| `moderate` | ≥2 reputable sources, measurable benefit, some HW variance | not required |
| `advanced` | Experimental, hardware-specific, or anecdotal | **required** |

Promotion rule: `evidence_level="experimental"` → `risk_level="advanced"` + non-None `risk_warning`.

**Measured exception (decided 2026-09-02) — there is no expert mode.** A setting whose
cost is security rather than frames (per-executable Control Flow Guard opt-out, a
Defender exclusion, a speculative-execution mitigation switch) is never shipped on
evidence from someone else's machine. It may be offered only after fpstune's own verify
round (`verify_round.measure_pair()` over `noise_floor()`) has measured a gain on *this*
machine; it then lands in `complete` with `risk_level="advanced"`, the cost written in
the copy, and the same undo as any other setting. Red lines stay red under every rule:
Secure Boot, HVCI / core isolation, driver signature enforcement, test-signing,
hardware-ID changes and kernel drivers are never offered, measured or not.

---

## Project Map

**Stack:** Python 3.12/FastAPI (uvicorn) + React 18/TypeScript/Vite/Tailwind | **Platform:** Windows 11 | **Deploy:** Local desktop
**Toolchain:** ruff + mypy | pytest + pytest-asyncio | Vite + vitest | lefthook (pre-commit) | PyInstaller

```
src/fpstune/
  api/      schemas.py (response models) · status_cache.py · hardware/ (network_adapters, storage, audio)
            routes/  settings.py · settings_apply.py · settings_stream.py · benchmark.py ·
                     system.py · system_{network,audio,power}.py · system_common.py ·
                     display.py · debug.py
  settings/ definitions/ (15 category files) · executors/ · base.py · applicability.py ·
            hardware_context.py · impact_categories.py · groups.py · registry.py ·
            performance_headroom.py · headroom_policy.py · cleanup_measure.py ·
            cleanup_targets.py · detection.py · discovery/ · panel.py · virtualization.py
  core/     BcdEdit, DISM, NV Inspector, power profiles
  safety/   restore.py (RestorePointManager) · originals.py
  benchmark/  suite.py (Bench/BenchReading/BenchResult/SuiteRun + the per-bench deadline) ·
            benches.py (the registry, and which benches a button may start) · verify_round.py ·
            sources.py (which claim each instrument answers, and why the rest are unanswered) ·
            ledger.py (the resumable job + the two persisted runs, ~/.fpstune/bench) ·
            scheduler.py (when to measure: idle, no game, no apply, lock free) ·
            operation_lock.py (the one named mutex an apply, a cleanup and a bench share) ·
            instruments: presentmon · gpu_scene (Superposition Basic driven windowed at the panel's
            native res, a fixed 30 s slice; downloads on first use, never bundled) · headroom_watch · sensors (GPU and ACPI temperature, and
            the thermal claims FurMark used to carry) · cpu_bench · memory · disk_io ·
            network · network_load (both directions; skipped unasked on a metered line) ·
            frame_pacing · timing_bench · dpc · event_scan · storage_health · gpu_memory ·
            boot_time · pcie_link · process_sampler · furmark (its own panel, verifies nothing)
  commands/ presentation.py (status lines, panels, banner, ASCII fallback) · scan.py
  utils/    console.py · runtime.py · detect.py · hardware_manager.py · admin.py · powershell.py
frontend/src/
  components/  SettingsTab · GameTweaksTab · CleanupPanel · HomeTab · TweakRows · TweakSetting ·
            SelectionToolbar · HardwarePanel · SettingInfoTooltip · SuitePanel · VerifyPanel ·
            ui/ConfirmDialog · ui/NotificationToasts
  store/    index.ts (AppSlice: selectedSettingIds, operationStatus, maintenanceSelection,
            cleanupResults, notifications) · settings.ts (SettingsSlice: flat
            Map<SettingId, Setting>, detection, selectors)
  lib/      api.ts · detection-manager.ts · hardware-manager.ts · tweakDomain.ts · impact.ts
```

UI surfaces: Home = what still needs optimizing plus reclaimable disk, one bulk action per
domain group · SettingsTab = Software Tweaks, flat list + filter bar · GameTweaksTab = one
section per game · CleanupPanel = rows grouped by `groupLabel` · TweakSetting = row with
checkbox, Radix tooltips, Verify/Revert, operationStatus badge · SelectionToolbar = sticky
bottom bar, bulk apply/reset via SSE, advanced-warning modal · HardwarePanel =
CPU/GPU/monitor/network/audio/storage · SettingInfoTooltip variants (info/hint/warning) ·
SuitePanel = Benchmarks > Measure, one button (baseline, then measure-and-compare) ·
VerifyPanel = Benchmarks > Verify (coverage, the suite's own pair, verdicts) ·
`lib/detection-manager.ts` = `redetectSettings()` orchestrator · `lib/hardware-manager.ts` =
monitor cache invalidation.

Route surface: `settings.py` = CRUD/detect/apply/reset/undo/verify/bulk · `settings_stream.py`
= `/bulk/stream-{apply,reset}` SSE (own router, `/api/settings` prefix) · `benchmark.py` =
run/compare + verify/{coverage,sources,sample,round} + headroom{,/measure} · `system.py` =
system/gpu/status/activity/hardware info, with `system_{network,audio,power}.py` as sub-routers
on `/api` and `system_common.py` = `_run_powershell_async`. Detail detection lives in
`api/hardware/`, which returns schema objects and declares no router.

Data flow: UI → api.ts `POST /settings/{id}/apply` → settings route → `executor.apply()` →
subprocess → `_finalize_apply_response()` → detect → verify → response → Zustand → UI.
SSE bulk: SelectionToolbar → bulkStreamApply/Reset → `/bulk/stream-{apply,reset}` →
`_stream_sequential()` → `asyncio.to_thread(apply)` per ID → events streamed → UI badges.

Module contracts — what the tree does not tell you:

- `routes/settings_apply.py` — no router. `apply_and_finalize` is the one place a setting's
  command runs for apply, reset and undo; it measures a cleanup's target either side of the
  command and hands the pair to `_finalize_apply_response`, looked up on `settings.py` at call
  time so the edge back is never a module-level import.
- `settings/definitions/` — 419 `SettingExecutor` instances across 15 category files.
- `definitions/game_configs_mw4.py` — MW4 (cod26); keys carry their `@scope` index, and ranges
  are adopted from the installed build at startup, never declared.
- `definitions/game_configs_mw3_profile.py` — MW3 (cod23) gamerprofile (audio, input, aim), the
  game's *second* config file; kept apart from `game_configs.py` because a key name can appear
  in both.
- `executors/` — Registry, PowerShell, Netsh, POWERCFG, NvProfile.
- `executors/nvidia_app.py` — NVIDIA App Battery Boost criteria: support, never state.
- `executors/game_config_writer.py` — the one `Name@scope` line rewriter, shared by both Call
  of Duty titles: LF endings, BOM round-trip, read-only clear, atomic replace with retry, the
  whole read-modify-write under one lock, and a refusal of any value the line's own `// range`
  forbids.
- `executors/mw4_config.py` — MW4 target; the scope digit is required, because `DxrMode@0`
  (Off/On) and `@1` (Off..Ultra) are two controls.
- `executors/mw3_profile.py` — MW3 gamerprofile target; the scope digit is *optional*, because
  that file ships in two live schemas: `Name@0 = v // range`, and the older `Name@ v // range`
  with a BOM, one per account dir.
- `executors/game_processes.py` — refuses a config write while that game is running; games
  flush settings from memory on exit, undoing a write that apply AND verify both passed.
- `settings/base.py` — `SettingExecutor` dataclass: risk_level, risk_warning, evidence_level,
  impact_scores. `module` is the first segment of the id.
- `settings/hardware_context.py` — `build_hardware_context()`, the one builder, API and CLI
  alike; `mobile` is derived from GetSystemPowerStatus, never from a model list.
- `settings/impact_categories.py` — metric key → kind of gain; thermal ranks with performance.
- `settings/performance_headroom.py` + `headroom_policy.py` — what a game measured against what
  the panel can show: band (met/near/short/critical) and which side the frame waited on. `met`
  raises the value, `short`/`critical` move the scope, the bottleneck picks which settings;
  `near` and unmeasured change nothing.
- `settings/cleanup_measure.py` — the one parse of a `ready|<size>` reading, plus the pair taken
  either side of a cleanup command; `freed_bytes` is that difference or nothing (C11 rule 3).
- `settings/discovery/` — one module per discoverer, each handed the `Registrar` protocol
  (register/get/get_all, nothing else); a new game is a new module plus one line in
  `all_discoverers()`, whose order is load-bearing.
- `settings/panel.py` — the one primary-panel derivation (primary_monitor, refresh_ceiling_hz,
  primary_refresh_hz); an unknown rate stays 0.
- `settings/detection.py` — parallel detection over a ThreadPoolExecutor.
- `benchmark/verify_round.py` — `judge(claim, measurement)` →
  verified/contradicted/inconclusive/unmeasured.
- `benchmark/headroom_watch.py` — decides *when* to measure: daemon poll for a running game,
  once per game session, plus the on-demand UI path. No archive — one entry per game in
  `~/.fpstune/headroom.json`, overwritten in place.
- `commands/scan.py` — one detection pass shaped by status/gpu; neither prints.
- `utils/console.py` — the one Rich Console; the logger writes through it.
- `utils/runtime.py` — frozen-vs-source packaging facts (sys._MEIPASS, bundled frontend).
- `TweakRows.tsx` — the one row list (apply/reset/undo/verify), shared by Software and Game.
- `ui/ConfirmDialog.tsx` — the one modal confirmation: role, focus trap, Escape, inert page.
- `ui/NotificationToasts.tsx` — the one reader of the store's `notifications`; two
  always-mounted live regions (assertive for errors and warnings, polite for the rest),
  keyboard-dismissed, never focus-stealing.
- `lib/api.ts` — `settingsApi`: applySetting, undoSetting, bulkApply, bulkStreamApply,
  bulkStreamReset. No `reset` client method — the row's reset posts `/apply` carrying
  `defaultValue`; no `verify` one has ever existed.

**Key invariants:**
- Profile system removed; scope (essential/recommended/complete) replaces it throughout
- `_finalize_apply_response()` is the single post-apply path — never bypass
- `values_equal()` (applicability.py) is the single comparison truth — never `==` for values
- `ABSENT_READINGS` (applicability.py) is the single sentinel set: an executor meaning "this is
  not on this machine" uses one of those spellings and nothing else, and detection turns every
  one into `is_applicable=False`. Never re-spell a sentinel locally; never list one in `choices`.
- HardwareManager is a singleton; always use the `hardware_manager` global.
  `start_hotplug_polling()` runs a 15s daemon thread
- SSE bulk: each ID runs in `asyncio.to_thread`; the event loop stays free between IDs
- **A setting that rewrites a whole shared file holds one lock for the entire
  read-modify-write.** Bulk apply runs in parallel (`api/routes/settings.py`, 16 workers);
  leave the read outside the lock and two writers both load the pre-change copy, the second
  silently dropping the first one's setting while both report success. The cache refresh
  belongs inside the lock too — the follow-up detect verifies against it, so a refresh from
  stale text confirms a value that is not in the file. Primitive: a named system mutex
  (`powershell_actions._MUTEX_GROUPS`, `mw4_config._file_lock`), with a process-local fallback
  where one cannot be created. Proven by
  `tests/test_executors/test_mw4_config.py::test_neither_setting_is_lost`.
- **The hardware / software / game split is a predicate, never `module`.** `module` is the id's
  first segment, so every game collapses to `game_config` and every system tweak to `system` —
  it cannot express a domain. `frontend/src/lib/tweakDomain.ts` holds the predicates
  (`isHardwareTweak`, `isGameTweak`, one per domain) and every surface asks it; Software is the
  leftover, so the three partition the registry and nothing lands twice. A new domain is a new
  predicate there, never an id-scheme change. Each list surface excludes the domains it does
  not own: Software Tweaks (flat list + filter bar), Game Tweaks (one section per game), Home's
  three groups and the tab badges all filter by predicate. Proven by `SettingsTab.test.tsx`
  ("leaves a game's config line to the Game Tweaks tab") and `GameTweaksTab.test.tsx`.
- **A heading is the backend's word, never the frontend's.** `settings/groups.py` resolves each
  setting's group — id-derived for a game (`game_config:mw4:x` → the label in
  `game_processes.GAME_LABELS`), declared for a cleanup — and `SettingDefinitionResponse`
  carries `group_id`, `group_label`, `group_order`. Game Tweaks and the cleanup panels render
  that label verbatim (C9), each heading selecting its own group. A setting in a grouped module
  with no group fails `tests/test_settings/test_groups.py`, so a new game or cleanup cannot
  land under no heading.
- `impact.ts` writes per-row benefit text from `impact_scores` — claims only, never a summed
  headline (C11 rule 1)

---

## Blueprint Profile

Type: desktop | Stack: python-3.12-fastapi + react-18-ts-vite | Target: production
Mission: On any Windows 11 machine, reach that machine's own measured ceiling — max fps plus IO/network/memory — through risk-free hardware-derived tweaks, holding every competitively informative visual/audio channel at its information-preserving minimum, with before/after measurement and single or bulk undo.
Priorities: frame-rate-first, measured-over-claimed, hardware-derived, reversibility, thermal-as-performance
Constraints: windows-11-primary, local-only-no-telemetry, single-exe-distribution, prefer-existing-deps
Red lines: no tweak that lowers the ceiling (C1), no number an instrument did not produce (C11), no dev-machine literal (C9), English-only strings (C4), no kernel driver / Defender-off / UAC-off, reset and undo never collapse into one (C6)
Integrations: none
Data: local system + hardware inventory, never leaves the machine | Regulations: none
Audience: public Windows 11 gamers (OSS) | Deploy: GitHub Releases single exe

Entry: src/fpstune/cli.py (click) + src/fpstune/api/main.py (FastAPI)
Modules: settings/definitions=registry(15 files, 419 settings); settings/executors=writers(13); api/routes=http(12); benchmark=instruments(17); core=system-mutators(7); commands=cli(8); frontend/src/components=ui(41)
Data Flow: UI → POST /api/settings/{id}/apply → executor.apply() → PowerShell/registry → _finalize_apply_response() → detect+verify → Zustand
External: PresentMon(frame capture); FurMark(thermal/stability); NVIDIA Profile Inspector(nv driver profiles); PowerShell/WMI(system state)
Toolchain: ruff+mypy+pytest / eslint+tsc+vitest | CI: github-actions (ci.yml, release.yml) | Container: none

Ideal: coupling=50 cohesion=70 complexity=12 coverage=70%

Scores: sec=47 quality=73 arch=59 perf=29 resil=71 test=37 stack=97 dx=93 docs=53 overall=60 model=claude-fable-5

## End Blueprint Profile
