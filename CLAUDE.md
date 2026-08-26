# FPSTune Project Rules

## Product Goal

On any Windows 11 machine, fpstune tunes every point of the system so the user
gets the best gaming experience **that machine and that internet connection are
capable of**. Not a preset, not a generic checklist — the ceiling of the actual
hardware and the actual line.

Five consequences that decide real arguments:

1. **Derive from the hardware, never assume.** The right value is whatever the
   device reports it can do: the panel's own max refresh, the adapter's own
   `ValidRegistryValues`, the driver's own keyword spelling, the NIC's own
   `NumericParameterMaxValue`. A hardcoded constant is a bug waiting for
   hardware that disagrees — `1024` buffers (#45), `1Gbps_Full` on a 2.5GbE
   adapter, `*AdvancedEEE` on a Realtek. Every one of those shipped and every
   one was wrong on real hardware.
2. **Leaving a default alone is a legitimate answer, and so is undoing.** A
   setting whose `recommended_value` equals its `default_value` is not dead
   weight: it is a guard that detects drift — from another "optimizer", from a
   guide, or from an earlier fpstune release — and puts the machine back.
   Reaching the ceiling means removing harm as often as adding tweaks.
3. **A tweak that can lower the ceiling is not a tweak.** This is C1 with teeth.
   Forcing link speed breaks auto-negotiation; a background frame cap can cap
   the foreground game. Both shipped as recommendations, and both cost the user
   far more than any tweak in the registry gained them.
4. **Heat is a performance category, not a comfort one.** Thermal throttling is
   how a frame rate decays, and the decay arrives in minute forty rather than at
   the moment of the tweak — which is why this class of damage survives so well.
   So anything that reduces heat or wear *without costing performance when it is
   wanted* is in scope: a menu frame cap, a 30 fps cap on an unfocused game, an
   idle core allowed to clock down. They belong under the `thermal` impact
   category ("Heat & wear" in the UI), never under `fps` — they do not raise a
   frame rate, they stop the machine arriving at the match already at its limit.
   The mirror rule holds too: `Minimum processor state = 100`, `Processor idle
   disable = 1` and NVIDIA's "Prefer maximum performance" all buy zero frames and
   cost heat all session, so undoing them is a tweak (see consequence 2).
5. **Frame rate is priority one; the minimum is the default answer, and only
   information earns more.** This is a rule about every tweak in the product,
   not only the ones inside a game's config file, and it decides who carries the
   burden of proof. The default position for any setting that costs frames is
   its lowest tier. Raising it is the exception, and the exception has to be
   argued in the setting's own copy: *this is something the player reads*.
   Enough visual quality to tell an opponent apart, enough audio quality to hear
   where a sound came from and what it was — and not one tier above that line,
   because everything above it is spectacle, and spectacle is what gets spent
   for frames.

   Two things follow that are easy to get backwards.

   **Spend only headroom you have measured.** A quality tier is bought with
   frames, so a machine that has not reached its own target has nothing to buy
   with. `headroom_watch` measures what each game actually achieves against what
   the panel can show; below that target the answer is the minimum tier that
   still carries the information, at the target the quality-leaning value is
   correct. A recommendation that costs frames on a machine measured at 19% of
   its target is not a trade-off, it is a regression — and it must never sit in
   `recommended` scope, where the user did not ask for it.

   **An information channel has its own minimum, and that minimum is the
   answer.** Deciding a setting is functional buys it the tier that carries the
   information — not the top of its list. A shadow drawn at `Low` still gives a
   corner away; particles at `low` still tell a grenade from a muzzle flash; a
   player model at `Medium` is still identifiable at range. So the question is
   never "is this information?" alone, it is *what is the lowest tier at which
   this still says what it says*, and the answer stops there. Reaching for the
   maximum because the channel matters spends frames on resolution the player
   never reads.

   **Minimum is not zero.** A preset that flattens spell effects buys frames and
   loses the fight, and `SoundSampleRate=22050` in a shipped config is a
   functional loss that raising is a *tweak*. The rule cuts upward exactly as
   often as it cuts down; what it never does is leave a setting high because the
   default was, or high because the channel is important.

   The line runs between **information and decoration**, not between high and
   low:

   | Functional — keep, and raise if it was lowered | Decorative — spend it |
   |---|---|
   | Model and texture detail on enemies | Bloom, depth of field, motion blur |
   | Ability and spell effects (a cast is *announced* by its particles) | Cloth, ragdoll, debris physics |
   | Audio sample rate and channel count — footstep direction is information | Cinematics, 3D portraits, water reflections |
   | Anything that changes what the player can *see coming* | Ambient occlusion, shadow softness in a game where shadows carry nothing |

   Scope follows from the side it lands on. A setting that costs nothing a
   player can perceive belongs in `ESSENTIAL`/`RECOMMENDED`; one that changes
   what the screen shows or what the player can hear belongs in `COMPLETE`, with
   the cost written in the copy — offered, never assumed.

   Which side a setting falls on is decided **per game**, not globally: shadows
   are decoration in an isometric MOBA and information in a first-person shooter
   where one is cast around a corner.

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

### C4 — English Only
All strings (UI, comments, errors, docs) in English.

One carve-out, and it is about evidence rather than language: a comment quoting
what Windows *printed back* keeps the quote verbatim. `ping.exe`,
`ValidDisplayValues` and `netsh wlan show interfaces` answer in the system
language, and those quoted strings are the entire reason each code path reads a
numeric enum (or, for WiFi, wlanapi.dll's own numbers) instead of the text —
paraphrasing them into English would delete the finding that justifies the code.

Gate: `tests/test_quality_gates.py::TestC4EnglishOnly`, which compares
characters and holds the carve-out to the exact quoted phrases. The shell form
this gate used to carry — `grep -rn "[çğıİöşüÇĞÖŞÜ]"` — matched byte by byte
under Git Bash and reported every `✓`, `°` and `±` as a Turkish letter, so it
could never come back clean and stopped being run. If you want it by hand:
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
- Detection never returns value outside `choices` tuple; `value_map` covers all raw outputs

Single-setting endpoints:
- `POST /settings/{id}/apply` — apply, detect, verify
- `POST /settings/{id}/reset` — write `default_value` (Windows stock), detect, verify
- `POST /settings/{id}/undo` — write the recorded original, detect, verify, then forget it;
  409 when nothing was recorded (never falls back to reset)
- `POST /settings/{id}/verify` — detect only → `VerifyResponse{matches, current_value, expected_value, target}`;
  `target` ∈ `recommended` (default) | `default` | `original` names which question was asked

Reset and undo are different promises and must never collapse into one: reset
writes the curated stock value, undo writes what this machine held. They agree
only on a machine that was stock to begin with. Originals are recorded by the
**full scan** (`POST /settings/detect`) and never by a single re-detect — that
one runs after an apply, and recording there would capture fpstune's own write.
First write wins; `safety/originals.py` persists to `~/.fpstune/originals.json`.

Bulk SSE endpoints:
- `POST /settings/bulk/stream-apply` — sequential SSE, events: started/applied/verified/failed/done
- `POST /settings/bulk/stream-reset` — same pattern for reset

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
Each `SettingExecutor` changes exactly 1 logical setting.
Named-compound exceptions (keep together):
- Mouse acceleration = 3 registry values → 1 concept ✅
- DNS = primary + secondary IP → 1 concept ✅
- Telemetry = 9 tasks + 1 registry key → 1 concept ✅
- DSCP QoS = NLA flag + NetQosPolicy entries → 1 concept ✅
- Browser cache cleanup = Edge/Chrome/Brave/Firefox → 1 concept ✅

Forbidden: bundling unrelated subsystems (e.g., `WaitToKillServiceTimeout` + `HungAppTimeout` + `AutoEndTasks`).
Split examples: `system:network_afd_receive_window` + `system:network_afd_send_window` (separate settings).
Gate: No `ACTION_COMMANDS` entry bundles >1 logical subsystem unless named-compound.

### C9 — Machine-Neutral: nothing about the developer's machine or account

C1 says derive values from the hardware. C9 says the same about **where things
live and who owns them**: every path, identifier and name a tweak touches is
*discovered at runtime*, never carried in the source. The product must behave
identically on a machine fpstune has never seen and under an account it has
never heard of.

Forbidden in source, tests, and fixtures — any literal that only exists because
of the machine it was written on:

| Class | Never hardcode | Discover instead |
|---|---|---|
| User & account | Windows username, `C:\Users\<name>`, game account/profile IDs (MW4's `playersBeta\<numeric account id>`) | `%LOCALAPPDATA%` + glob the profile dir |
| Install location | `D:\<user-named library>\...`, any drive letter, any library path | Steam/Battle.net/Epic registry + library folders |
| Build-tagged paths | `playersBeta`, `bt.cod26` — beta names that change at release | glob the pattern, take newest match |
| Display | monitor model (the dev panel's own name), resolution, refresh rate | EDID/WMI, panel's own max |
| GPU/CPU | model string, VRAM size, thread count, driver version | `detect.py`, `hardware_context` |
| Config key suffixes | MW4's `@0;14317;21371` hashes | read the line, preserve the suffix verbatim |

Two rules that follow:

1. **Match on the stable part, preserve the volatile part.** For MW4, the key is
   `Name@<scopeIndex>` — the scope index disambiguates (`DxrMode@0` is Off/On,
   `DxrMode@1` is Off..Ultra) while the trailing hashes are copied through
   untouched. Never reconstruct a key you did not read.
2. **A file's own metadata beats a constant.** MW4 ships `// 0 to 3` and
   `// one of Low, High` on every line; those are the range and the `choices`.
   A hardcoded range is a bug waiting for the next patch.

Gate: `tests/test_quality_gates.py::TestC9MachineNeutral`, which runs against
executable lines of shipped source only. Two exclusions, both deliberate: the
same literals are legitimate in a comment documenting *why* a code path exists,
and in a test as fixture input — passing this machine's panel name *in* as an
argument is the opposite of reading it out of the environment.

The shell form this gate used to carry could express the first exclusion and not
the second, so it flagged `MonitorCard.test.tsx` for a fixture the prose above
declares fine. By hand, with both (each scrubbed literal is spelled with a
character class so this document never contains it — the history scrub requires
zero tree-wide hits, and `grep -E` reads the two spellings identically):

```bash
grep -rnE "(Q25G4[S]|41613607[3]|Oyunla[r]|RTX 307[0]|i7-11800[H]|Users\\\\[A-Za-z])" \
  --include="*.py" --include="*.ts" --include="*.tsx" \
  --exclude-dir=__pycache__ --exclude-dir=__tests__ \
  --exclude="*.test.ts" --exclude="*.test.tsx" \
  src/ frontend/src/ | grep -vE ":[0-9]+:[[:space:]]*(#|//)"
```

### C10 — Vendor & Platform Complete

"Best that machine is capable of" is a promise to *every* machine, so a feature
that only works on the developer's silicon is unfinished, not shipped. Each
setting must be correct on all three GPU vendors, on any CPU, and on every
Windows 11 edition — where "correct" includes *knowing it does not apply*.

- **Symmetry.** A vendor-specific concept ships for all vendors or is named as a
  gap: upscaling = DLSS **and** FSR **and** XeSS; low-latency = Reflex **and**
  Anti-Lag 2 **and** XeLL; frame generation = DLSS-FG **and** FSR-FI **and**
  XeSS-FG. Registering only the NVIDIA half leaves AMD and Intel users a
  measurably worse ceiling.
- **Not-applicable is a first-class answer.** A setting that cannot apply
  reports an `ABSENT_READINGS` sentinel → `is_applicable=False`. It never writes
  a value the hardware will reject and never shows a control that does nothing.
- **CPU/GPU capability, not model lists.** Thread counts, core counts, VRAM,
  P/E-core split and `mobile` come from detection. A model-name allowlist is
  the same bug as a hardcoded constant.
- **Editions and form factors.** Home lacks BitLocker cmdlets; laptops have a
  battery and a thermal ceiling desktops do not; a 60 Hz panel and a 500 Hz
  panel derive different caps from the same rule.

Gate: for every vendor-specific setting, either a sibling exists for the other
two vendors or `tasks.md` records the gap with a reason.

### C11 — Measured, or Not Claimed

Every number a user is shown is either something an instrument produced on *that*
machine, or it is not shown. There is no third option, and "derived from what the
settings claim" is the second one wearing the first one's clothes.

The gate exists because this exact mistake shipped three times, and all three are
written down in the code that fixed them:

| What shipped | Why it could not mean anything |
|---|---|
| `"GAINED -683ms LATENCY"` | DNS lookup, mouse polling, timer resolution and NIC buffering are different clocks over different events; their sum has no referent (`impact.ts`, `latencyTweaks`) |
| `dns_security`'s `-12 ms` | a millisecond figure nobody ever measured, on a setting whose benefit is not a latency |
| `"Gained +28-45% FPS"` | every setting's claimed fps midpoint summed under an invented decay curve, on a machine `headroom.json` measures at 19% of its own target |

Seven rules follow.

1. **A sum of claims is not a measurement.** Adding `impact_scores` up and
   presenting the total as a result is forbidden anywhere a user can see it.
   `impact_scores` is what a setting *claims*; only `benchmark/` produces what a
   machine *did*.
2. **A measurement is a list of samples, not a number.** A difference whose noise
   floor could not be computed is not a difference. `verify_round.measure_pair()`
   over `noise_floor()` is the one comparison path — a single reading yields
   infinite noise and therefore no verdict, deliberately.
3. **What could not be measured says so.** A bench never drops out quietly: it
   returns `ran=False` with a `reason` a user can read. This is `sources.py`'s
   "here is why we cannot check that" extended from claim coverage to the whole
   measurement surface.
4. **A qualitative claim is not a missing instrument.** `privacy`,
   `target_visibility`, `footstep_clarity`, `ux`, `security` are real claims that
   no benchmark adjudicates. They are their own class of unmeasurable, never
   filed under "states no number" or "no instrument" — filing them as gaps
   invents a to-do that can never be closed.
5. **Every area we improve gets an instrument, or the gap is on the record.**
   Any impact metric a shipped setting claims has either a source in `SOURCES` or
   a named reason in `NO_INSTRUMENT`. There is no silent third state.
6. **A stress test is not a performance test.** FurMark is a power virus: it
   answers "how hot, how stable", never "what does this machine reach". It stays
   off the performance path and keeps its own panel.
7. **A vendor-neutral instrument beats a vendor's wrapper.** C10 applied to tool
   choice: PresentMon reads all three vendors, so FrameView — board power on
   NVIDIA, chip power only on AMD — would be a regression however much nicer it
   looks.

The load may vary (a real game, our own scene); the instrument does not. That is
what keeps "max settings here, low settings there" a single comparison on a
single axis.

Bindings, because a rule nothing enforces is decoration:

| Rule | Bound by |
|---|---|
| 1 | `tests/test_quality_gates.py` (this gate's own paths resolve) + the red-proven test landing with the headline rewrite |
| 2 | `tests/test_benchmark/test_verify_round.py` |
| 3 | `tests/test_benchmark/test_sources.py` |
| 4, 5 | `NO_INSTRUMENT` in `src/fpstune/benchmark/sources.py` + its tests |
| 6, 7 | the composition of `SOURCES` in `src/fpstune/benchmark/sources.py` |

A clause with no binding yet names, in `tasks.md`, the step that gives it one —
the same escape hatch C10 uses. A clause that can never be bound is not written.

---

## Risk Taxonomy

Every `SettingExecutor` carries `risk_level`. All tweaks (including `advanced`) are shown; `advanced` settings surface their per-setting `risk_warning` inline in the UI.

| Level | Meaning | `risk_warning` |
|---|---|---|
| `safe` | No side-effects, proven all hardware | not required |
| `low` | Default; well-understood, rare edge-case | not required |
| `moderate` | ≥2 reputable sources, measurable benefit, some HW variance | not required |
| `advanced` | Experimental, hardware-specific, or anecdotal | **required** |

Promotion rule: `evidence_level="experimental"` → `risk_level="advanced"` + non-None `risk_warning`.

---

## Project Map

**Stack:** Python 3.12/FastAPI (uvicorn) + React 18/TypeScript/Vite/Tailwind | **Platform:** Windows 11 | **Deploy:** Local desktop

```
src/fpstune/
  api/
    routes/settings.py   detect, apply, reset, undo, verify, bulk/stream-apply, stream-reset
    routes/benchmark.py  run/compare + verify/{coverage,sources,sample,round} + headroom{,/measure}
    routes/system.py     GPU/CPU/network/audio/storage hardware info
    routes/display.py    monitor detection + config
    routes/debug.py      admin+debug mode only
    status_cache.py      background refresh, cached status
    hardware/            network_adapters/storage/audio detection that returns schema
                         objects and declares no router — under api/ because of the
                         schemas, outside routes/ because nothing here is a route
  settings/
    definitions/         395 SettingExecutor instances across 14 category files
    definitions/game_configs_mw4.py  MW4 (cod26); keys carry their `@scope` index, ranges
                         are adopted from the installed build at startup, not declared
    executors/           Registry, PowerShell, Netsh, POWERCFG, NvProfile
    executors/nvidia_app.py  the NVIDIA App's own Battery Boost criteria — support, never state
    executors/mw4_config.py  MW4 (cod26) writer: one `Name@scope` line, byte-level so the
                         file's LF endings and absent BOM survive; rejects a value the
                         file's own `// range` comment does not allow
    executors/game_processes.py  refuses a config write while that game is running —
                         games flush settings from memory on exit, so such a write is
                         undone after apply AND verify have both reported success
    base.py              SettingExecutor dataclass: risk_level, risk_warning, evidence_level, impact_scores
    applicability.py     values_equal() + ABSENT_READINGS (the one sentinel set) + HardwareContext
    hardware_context.py  build_hardware_context() — the one builder, used by API and CLI alike;
                         `mobile` is derived here from GetSystemPowerStatus, never from a model list
    impact_categories.py metric key → kind of gain (thermal ranks with the performance categories)
    groups.py            which heading a setting renders under (its game, its kind of
                         cleanup) — a game's own id supplies it, a cleanup declares it
    performance_headroom.py  what a game measured against what the panel can show: the
                         band (met/near/short/critical) and which side the frame waited on
    headroom_policy.py   what a band and a bottleneck are allowed to change — `met` raises
                         the value, `short`/`critical` move the scope, the bottleneck picks
                         which settings; `near` and unmeasured change nothing
    detection.py         Parallel detection, ThreadPoolExecutor
    discovery/           one module per discoverer, each handed the `Registrar` protocol
                         (register/get/get_all and nothing else) rather than the registry
                         itself; a new game is a new module plus one line in
                         `all_discoverers()`, whose order is load-bearing
    panel.py             the one primary-panel derivation (primary_monitor,
                         refresh_ceiling_hz, primary_refresh_hz) — an unknown rate stays
                         0 and never becomes 60
  core/                  BcdEdit, DISM, NV Inspector, power profiles
  safety/restore.py      System Restore point creation/listing (RestorePointManager)
  safety/originals.py    First-seen value per setting (~/.fpstune/originals.json), for undo
  benchmark/             PresentMon, FurMark, DPC latency
    verify_round.py      judge(claim, measurement) → verified/contradicted/inconclusive/unmeasured
    sources.py           which claim metrics each instrument can measure, and why the rest cannot
    headroom_watch.py    decides *when* to measure — daemon poll for a running game, once per
                         game session, plus the on-demand path the UI button calls. No archive:
                         one entry per game in ~/.fpstune/headroom.json, overwritten in place
  commands/
    presentation.py      the terminal vocabulary (status lines, panels, banner, ASCII fallback)
    scan.py              one detection pass, shaped by status/gpu — neither prints
  utils/
    console.py           the one Rich Console; the logger writes through it too
    runtime.py           frozen-vs-source packaging facts (sys._MEIPASS, bundled frontend)
    detect.py            GPU/CPU/monitor detection with module-level cache
    hardware_manager.py  Singleton; start_hotplug_polling(15s daemon thread)
    admin.py             is_admin() check
    powershell.py        subprocess runner with UTF-8 + timeout

frontend/src/
  components/
    SettingsTab.tsx       Software Tweaks: flat list + filter bar; excludes hardware and game domains
    GameTweaksTab.tsx     Game Tweaks: one section per game, headed by the backend's `groupLabel`
    CleanupPanel.tsx      Cleanup rows grouped by `groupLabel`, each heading selecting its own group
    HomeTab.tsx           Home: what still needs optimizing and what disk is reclaimable,
                          one bulk action per domain group
    TweakSetting.tsx      Row: checkbox, Radix tooltips, Verify/Revert buttons, operationStatus badge
    TweakRows.tsx         The one row list (apply/reset/undo/verify), shared by Software and Game
    SelectionToolbar.tsx  Sticky bottom bar: bulk apply/reset via SSE, advanced warning modal
    HardwarePanel.tsx     CPU/GPU/monitor/network/audio/storage display
    SettingInfoTooltip.tsx  Info tooltip with variant (info/hint/warning)
    ui/ConfirmDialog.tsx  The one modal confirmation: role, focus trap, Escape, inert page
    ui/NotificationToasts.tsx  The one reader of the store's `notifications`; two
                          always-mounted live regions (assertive for errors and warnings,
                          polite for the rest), dismissed by keyboard, never focus-stealing
    SuitePanel.tsx        Benchmarks > Measure: one button — baseline, then measure-and-compare
    VerifyPanel.tsx       Benchmarks > Verify: coverage first, then the suite's own pair, then verdicts
  store/
    index.ts             AppSlice: selectedSettingIds, operationStatus, maintenanceSelection,
                         cleanupResults, notifications (capped, id-sequenced)
    settings.ts          SettingsSlice: flat Map<SettingId, Setting>, detection, selectors
  lib/
    api.ts               settingsApi: applySetting, undoSetting, bulkApply, bulkStreamApply,
                         bulkStreamReset. No `reset` client method — the row's reset posts
                         `/apply` carrying `defaultValue`; no `verify` one has ever existed
    detection-manager.ts redetectSettings() orchestrator
    hardware-manager.ts  monitor cache invalidation
    tweakDomain.ts       the one place a tweak's domain is decided — predicates over the
                         setting, never over `module` (see Key invariants)
    impact.ts            per-row benefit text from `impact_scores`; claims only, and
                         claims never add up to a headline (C11 rule 1)

Data flow: UI → api.ts POST /settings/{id}/apply → settings route → executor.apply() → subprocess
          → _finalize_apply_response() → detect → verify → response → Zustand update → UI refresh

SSE bulk flow: SelectionToolbar → bulkStreamApply/Reset → /bulk/stream-{apply,reset}
          → _stream_sequential() → asyncio.to_thread(apply) per ID → events streamed → UI badges
```

**Toolchain:** ruff + mypy | pytest + pytest-asyncio | Vite + vitest | lefthook (pre-commit) | PyInstaller

**Key invariants:**
- Profile system removed; scope (essential/recommended/complete) replaces it throughout
- `_finalize_apply_response()` is the single post-apply path — never bypass
- `values_equal()` is the single comparison truth — never use `==` for setting values
- `ABSENT_READINGS` (applicability.py) is the single sentinel set — an executor that
  means "this is not on this machine" uses one of those spellings and nothing else,
  and detection turns every one of them into `is_applicable=False`. Never re-spell a
  sentinel locally, and never list one in `choices`.
- HardwareManager is a singleton; always use `hardware_manager` global, never instantiate
- SSE bulk: each ID runs in `asyncio.to_thread`; event loop must stay free between IDs
- **A setting that rewrites a whole shared file holds one lock for the entire
  read-modify-write.** Bulk apply runs in parallel (`api/routes/settings.py`, 16
  workers). Leave the read outside the lock and two writers both load the
  pre-change copy; the second one silently drops the first one's setting, and
  both report success. The cache refresh belongs inside the lock too — the
  follow-up detect verifies against it, so a refresh from stale text confirms a
  value that is not in the file. Primitive: a named system mutex
  (`powershell_actions._MUTEX_GROUPS`, `mw4_config._file_lock`), with a
  process-local fallback where one cannot be created. Proven by
  `tests/test_executors/test_mw4_config.py::test_neither_setting_is_lost`.
- **The hardware / software / game split is a predicate, never `module`.**
  `SettingExecutor.module` is the first segment of the id (`base.py`), so every
  game collapses to `game_config` and every system tweak to `system` — it cannot
  express a domain. `frontend/src/lib/tweakDomain.ts` holds the predicates —
  `isHardwareTweak` and `isGameTweak`, one per domain — and every surface asks
  it. Software is the leftover, so the three partition the registry and nothing
  lands twice. A new domain is a new predicate there, never an id-scheme change.
  Each list surface must exclude the domains it does not own: Software Tweaks,
  Game Tweaks, Home's three groups and the tab badges all filter by predicate.
  Proven by `SettingsTab.test.tsx` ("leaves a game's config line to the Game
  Tweaks tab") and `GameTweaksTab.test.tsx`.
- **A heading is the backend's word, never the frontend's.** `module` cannot name
  a game, so `settings/groups.py` resolves each setting's group — id-derived for
  a game (`game_config:mw4:x` → the label in `game_processes.GAME_LABELS`),
  declared for a cleanup — and `SettingDefinitionResponse` carries `group_id`,
  `group_label`, `group_order`. Game Tweaks and the cleanup panels render that
  label verbatim (C9). A setting in a grouped module with no group fails
  `tests/test_settings/test_groups.py`, so a new game or cleanup cannot land
  under no heading.

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
Modules: settings/definitions=registry(14 files, 395 settings); settings/executors=writers(13); api/routes=http(12); benchmark=instruments(17); core=system-mutators(7); commands=cli(8); frontend/src/components=ui(41)
Data Flow: UI → POST /api/settings/{id}/apply → executor.apply() → PowerShell/registry → _finalize_apply_response() → detect+verify → Zustand
External: PresentMon(frame capture); FurMark(thermal/stability); NVIDIA Profile Inspector(nv driver profiles); PowerShell/WMI(system state)
Toolchain: ruff+mypy+pytest / eslint+tsc+vitest | CI: github-actions (ci.yml, release.yml) | Container: none

Ideal: coupling=50 cohesion=70 complexity=12 coverage=70%

Scores: sec=47 quality=73 arch=59 perf=29 resil=71 test=37 stack=97 dx=93 docs=53 overall=60 model=claude-fable-5

## End Blueprint Profile

Route module map (post-split): `system.py` = system/gpu/status/activity/hardware info routes; `system_network.py`, `system_audio.py`, `system_power.py` = sub-routers (all `/api` prefix); `system_common.py` = `_run_powershell_async`; detail detection moved out of `routes/` entirely, to `api/hardware/`. `settings.py` = CRUD/detect/apply/bulk; `settings_stream.py` = `/bulk/stream-{apply,reset}` SSE (own router, `/api/settings` prefix); response models in `api/schemas.py`.
