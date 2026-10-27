# The principle catalogue, applied

This is fpstune's application of `ilke-katalogu.md` (draft 1, 2026-10-25; G24/G27),
the 56-principle catalogue with its profiles, audit tools and brakes. The
catalogue states a principle, an operational meaning, a violation example and a
mechanical audit; this document states, for every one of them, what it means in
this repository and **what fails when it is broken**.

A principle with no mechanical binding is a sentence nobody runs, which is the
failure mode the catalogue itself names. So the rule for this document is:

* **Bound** — a command, test or tool fails when the principle is violated. The
  binding is named and, where it has a threshold or an allowlist, the threshold
  may only shrink (every baseline here has a stale check; a baseline that stops
  matching is a failure, not a licence).
* **Judgment** — no instrument can decide it, and the row says which review
  question stands in its place, with the evidence this repository has produced
  for it.
* **N/A** — the catalogue's own profile does not apply to a local-only Windows
  11 desktop tool, and the row gives the evidence for that decision rather than
  leaving the principle silently unimplemented.

Columns below: **Here** = the operational meaning for fpstune; **Bound by** =
what fails; **Brake** = the catalogue's counter-principle (what stops the
principle from being taken too far), applied.

The catalogue's common measure is *probability × impact, against effort*. That
is also how this document was prioritised: the bindings that catch a class of
bug (silent swallows, layer inversions, unmeasured claims, unbounded diffs) are
in; the bindings that would cost a subsystem to police a style preference are
judgment rows with the reason written down.

---

## A. Structure and design

| ID | Name | Here | Bound by | Brake |
|---|---|---|---|---|
| **P-SSOT** | Single source of truth | One home per fact: `values_equal`, `ABSENT_READINGS`, `user_paths`, `hardware_manager`, the registry, the bulk planner, the console, the panel derivation, the i18n catalogues. Unavoidable copies have a drift test. | `tests/test_principles_single_source.py` (each concept defined once, home not stale, profile roots read only through the resolver); `.jscpd.json` duplication threshold wired in `scripts/quality.sh`; the existing invariants in `CLAUDE.md` are themselves bound by `tests/test_quality_gates.py`, `tests/test_settings/test_domain.py`, `tests/test_settings/test_groups.py` and the typed `frontend/src/i18n` catalogues | P-RULE3 |
| **P-DRY** | Don't repeat yourself | A second copy uses the first. Known duplicates are counted, not tolerated: Steam install-path spellings and the DEVMODE struct have ceilings. | `.jscpd.json` (clone threshold 0.5 %; baseline 3 clones / 0.06 %); `tests/test_quality_gates.py::TestDuplicationCeiling` for the named copies | P-RULE3 |
| **P-RULE3** | Abstract at the third | No abstraction before the third real repetition. The catalogue makes this the brake on DRY, so it is judgment, not a gate: a factory/registry lands with the third caller, not the first. | Judgment — review question: "name the three call sites." The registry, `SOURCES`, `GAME_LABELS` and the discovery `DISCOVERERS` table are the cases where the third repetition did arrive | — (brake) |
| **P-SRP** | Single responsibility | A module changes for one reason. Route modules do not build the registry or create restore points; long functions and route modules have ceilings that only shrink. | `.importlinter` contracts; `tests/test_quality_gates.py::TestRouteLayering`, `::TestFunctionLengthCeiling`, `::TestRouteModuleCeiling`; `frontend/.dependency-cruiser.cjs` | P-KISS |
| **P-SOC** | Separation of concerns | Data and rules vs. presentation and I/O: API → settings/benchmark → core → utils, one direction; the UI renders backend labels (C9) instead of deciding them. | `.importlinter`; `TestRouteLayering`; `frontend/.dependency-cruiser.cjs`; `tests/test_settings/test_groups.py` (a heading is the backend's word) | P-KISS |
| **P-OCP** | Open for extension | A new setting is one `SettingExecutor` entry in `settings/definitions/`; a new game is one module plus one `DISCOVERERS` entry; a new game/cleanup group is derived from `GAME_LABELS` or declared in `groups.py`; a new bench claim is one `SOURCES` entry. | `tests/test_settings/test_groups.py` fails a grouped setting with no heading; `tests/test_settings/test_nvidia_choices.py` pins the discovery order; judgment for "a new axis or a new switch?" (the frontend's closed enums are deliberate: a new device kind is two files, a new tab three) | P-YAGNI |
| **P-LSP** | Liskov substitution | Small hierarchy, no override that narrows a contract: protocols (`Registrar`, discoverers) are structural; the `SettingExecutor` is a frozen dataclass, not a base class with abstract holes. | `tests/test_principles_architecture.py` (no project subclass raises `NotImplementedError`; every concrete `BaseExecutor` defines `detect` and `apply`) | P-KISS |
| **P-ISP** | Narrow interfaces | A discoverer sees `Registrar`'s three methods and nothing else; API responses are per-route models, not one god object; frontend components take the props they read. | `Registrar` protocol (`settings/discovery/__init__.py`); `tests/test_principles_architecture.py` pins the protocol at three methods; `api/schemas.py` per-surface models (A11 modelled every response) | P-YAGNI |
| **P-DIP** | Depend on abstractions | Dependency direction points inward: the API imports the domain, never the reverse; the benchmark daemon does not import a FastAPI route module at import time. Exceptions are named with reasons and may only shrink. | `.importlinter` contracts plus `tests/test_principles_architecture.py` (exception list shrink-only, stale-checked); `frontend/.dependency-cruiser.cjs` layer rules | P-YAGNI |
| **P-COHESION** | High cohesion, low coupling | Things that change together live together; cross-package edges are few and declared. Module ceilings keep a file from becoming two. | `.importlinter`; `TestFunctionLengthCeiling`; `TestRouteModuleCeiling`; `frontend/.dependency-cruiser.cjs` | P-KISS |
| **P-DEMETER** | Talk to your neighbours | No `a.b.c.d.e` chains in shipped code; ask the owner instead. | `tests/test_principles_code.py` (AST attribute-chain depth, allowlist shrink-only) | P-KISS |
| **P-COMPOSE** | Composition over inheritance | Behaviour is assembled, not inherited. No deep class trees in backend or frontend. | `tests/test_principles_architecture.py` (one project base at most; the allowlist is empty); the frontend has six classes, only two `extends` (React's `Component`, `Error`) | P-YAGNI |
| **P-ILLEGAL** | Illegal states unrepresentable | Finite states are enums/`Literal`s: `risk_level`, `evidence_level`, `scope`, `DetectType`, benchmark verdicts, API response models. Free-string state is a finding. | `tests/test_principles_code.py` (finite-state fields typed as `Literal`/enum); `mypy --strict`; TypeScript unions in `frontend/src` | P-KISS |
| **P-PARSE** | Parse, then validate | External input is parsed once at the boundary into typed objects: FastAPI + Pydantic for requests, the response models for what leaves, the command templates for what reaches PowerShell. Inside, no re-validation of the same shape. | `tests/test_principles_code.py` (every route declares a typed body/response; no raw `request.json()` parsing); `tests/test_api` contract tests; `tests/test_principles_ops.py` OpenAPI characterization (P-HYRUM) | P-KISS |
| **P-FCIS** | Functional core, imperative shell | The measurement core takes data in and returns a verdict; the instruments at the edge do I/O. `verify_round.judge`, `noise_floor`, `performance_headroom`'s band derivation and `bulk_plan.plan_lanes` are pure. | Judgment + structure: those modules are the mutation targets (`scripts/mutation.sh`) and are exercised by `tests/test_benchmark/test_verify_round.py`, `tests/test_settings/test_bulk_plan.py`; `.importlinter` keeps the I/O packages at the edge | P-KISS |
| **P-CQS** | Command–query separation | A reading does not change state. Detection may cache (a documented command-shaped exception); a `get_`/`read_`/`detect_` function that writes a value is a finding. | `tests/test_principles_code.py` (query-named functions must not write files/registry; allowlist with reasons) | P-KISS |
| **P-IDEMP** | Idempotent operations | Apply → detect → verify converges: applying the recommended value twice leaves the same state; scripts (`sync_version`, `update_winget_manifest`, the apply sweep) can run twice; webhooks/retries are not a concept here (no server). | `tests/test_api/test_idempotency_gate.py::TestApplyTwiceEqualsApplyOnce` (apply twice equals apply once, and verify agrees); the sweep's dry-run/post-settle round-trip (`tests/test_settings/test_apply_sweep_rules.py`, `tests/test_windows_contract/test_apply_roundtrip.py`); `tests/test_settings/test_power_plan_row.py::test_applying_twice_reuses_the_plan` | P-YAGNI |
| **P-POLA** | Least astonishment | A name says what it does; no hidden write behind `validate()`. The CQS binding is the mechanical half; naming is review. | Judgment — review question: "what does the caller think this does?" The CQS test catches the hidden-write form | — |
| **P-EXPLICIT** | Explicit over implicit | Errors are not swallowed: no bare `except: pass`, no silent `continue`; a broad except must carry its reason. | `ruff` with `BLE`, `S110`, `S112` (wired in `pyproject.toml` and `scripts/quality.sh`); `frontend/eslint.config.js` `no-empty`; `mypy --strict` | P-KISS |

## B. Simplicity and necessity

| ID | Name | Here | Bound by | Brake |
|---|---|---|---|---|
| **P-YAGNI** | You aren't gonna need it | No option, flag or extension point without a present requirement or a measured bug. | `vulture` over `src/fpstune` (`scripts/quality.sh`); `knip` over `frontend/src` (`npm run knip`); review question: "what requirement does this serve?" | — (brake) |
| **P-KISS** | Keep it simple | Between two correct designs, the one with fewer parts wins: files, layers, dependencies, state, configuration. | `ruff` `C901` with the catalogue's complexity ceiling of 20; `TestFunctionLengthCeiling`; `TestRouteModuleCeiling`; ESLint `complexity: 20` | — (brake) |
| **P-DELETE** | Delete first | Code is a liability: unused exports, dead flags and dead files go. | `vulture`; `knip`; `settings/retired.py` (every removed setting id and what became of it — a removal is recorded, never silent); `tests/test_settings/test_retired.py` + `registered_ids.txt` | P-CHESTERTON |
| **P-CHESTERTON** | Chesterton's fence | Before removing a guard, find why it was put there and write the reason in one line. `retired.py` is the record; a removal without an entry fails the suite. | `tests/test_settings/test_retired.py` (an id that leaves without an entry fails); PR template checkbox; judgment for the "why" itself | — (brake) |
| **P-GALL** | Gall's law | A working simple system evolves into a complex one; complexity is not built up front. | Judgment — the one-process API, the flat settings registry and the single-exe build are the evidence; a proposal that adds a service, queue or database must answer "what works today that this breaks" | — (brake) |
| **P-GOLDPLATE** | No gold-plating | Nothing beyond the acceptance criterion. A feature the request did not name does not ship. | Judgment — PR template asks for the acceptance criterion; this application itself is scoped by the catalogue's own measure (probability × impact vs. effort) | — (brake) |
| **P-SPECGEN** | No speculative generality | No generalisation without a second real use: no "database-independent layer" for one database, no plugin point with no plugin. | `vulture` + `knip` catch the code; judgment catches the shape (review question: "name the second caller") | — (brake) |
| **P-BOYSCOUT** | Boy-scout rule | Leave the touched line cleaner; unrelated cleanup goes to the work queue, not the same diff. | `scripts/diff_budget.py` (staged/branch diff budget: files and lines, offenders printed); `scripts/controls.py` runs it at pre-commit; review | P-YAGNI |

## C. Failure and security

| ID | Name | Here | Bound by | Brake |
|---|---|---|---|---|
| **P-FAILFAST** | Fail fast | Bad input is refused at the boundary, before anything binds, writes or serves: an out-of-range `--port`/`--ui-port`, a malformed env value, a definition with an inverted driver range. | `tests/test_principles_ops.py::TestPFailFast` (`serve --port -1|0|65536` and `--ui-port 70000` exit 2 naming "1 to 65535" before the banner or any bind); `SettingExecutor`/`DriverGate` `__post_init__` raises at registry build; `mypy --strict` | P-POSTEL |
| **P-FAILCLOSED** | Fail closed | When the permission/elevation answer is unknown, the write does not happen: `require_admin` refuses before the wrapped write, a declined elevation exits without starting, and the network-disable / storage-optimize routes answer 403 with no write. | `tests/test_principles_ops.py::TestPFailClosed`; `utils/admin.py` (`require_admin`, `require_admin_or_elevate`); the apply path's refusal classification in `utils/operation_log.py` | P-ERRBUDGET |
| **P-LEASTPRIV** | Least privilege | The app runs as the user and asks for elevation only on the rows that need it; CI workflows hold `permissions: contents: read` at workflow level (the publish job asks for its own writes), every action is pinned to a commit SHA, and no checkout leaves its token on disk. | `zizmor` over `.github/workflows` — 27 findings → 0 (`scripts/quality.sh`, CI); `tests/test_principles_ops.py::TestPLeastPriv` (pin shape, tag comment, permissions, `persist-credentials: false`, no release cache, self-reference, shrink-only allowlist, live zizmor run); `tests/test_quality_gates.py` (no kernel driver, no Defender/UAC off) | P-KISS |
| **P-DEPTH** | Defence in depth | **N/A as a deployment concern** (personal data / payment). There is no remote trust boundary, no account and no payment: the API binds loopback only, so the personal data it does hold (MAC/IP/SSID from `/api/hardware`) never leaves the machine and is never persisted. The local equivalent already exists as independent layers — loopback bind, Host-header assertion (DNS rebinding), Origin refusal on mutating verbs, CORS only for a source checkout's dev origins, no authn by design. | Evidence: `api/main.py` (`_LOOPBACK_HOSTS`, `_NO_TELEMETRY`), `tests/test_api/test_main_security.py`, `tests/test_principles_ops.py::TestPFailClosed`; a second authorization control would duplicate the same loopback check (P-YAGNI) | P-ONECHECK |
| **P-SECRETS** | Secret hygiene | No secret in the repo, logs or fixtures; if one is ever needed it comes from the environment. | Local gate: `tests/test_principles_security.py`, a dependency-free scan of every tracked file (private keys, provider tokens, credentials in URLs) with a detector self-test. CI gate of record: `.gitleaks.toml` (default rules inherited, no allowlist) with the real scanner — not a project dependency, so a contributor never needs it to commit. C9 gate | — |
| **P-12FACTOR** | Config in the environment | Everything that varies by machine or run is an environment variable, documented in `.env.example`; paths are resolved by `utils/user_paths.py`, never carried in source. | `tests/test_principles_security.py` (the set of `FPSTUNE_*` variables read in `src/` equals the set documented in `.env.example`; endpoint-host and IP-literal allowlists with a reason each; no credentials in URLs; no plain `http` off loopback; C9: `Path.home()`/`expanduser` only in the resolver); C9 gate | P-YAGNI |
| **P-PRIVACY** | Privacy by default | Local-only: no telemetry, no network unless the user asks for an update check or a bench download; the support log carries no user path, username or previous value. | `tests/test_principles_security.py` (behavioural: the support log masks resolved profile roots and any `X:\Users\<name>` while HKLM paths stay legible; no current/default/previous value keys; no command/stdout text; rotation stays five; a static scan forbids passing commands/argv to the log); `utils/operation_log.py`; C6 log rules | P-KISS |
| **P-POSTEL** | Robust in, strict out | The one outbound protocol (GitHub release check in `utils/updates.py`) is strict about what it sends and tolerant about what it receives: one constant HTTPS GET, exactly Accept + User-Agent; unknown fields, null assets, non-dict entries and a missing tag become a classified error, not a crash; 403/404/URLError/timeout/unreadable JSON become `UpdateCheck.error`; versions compare as numeric tuples (0.10.0 > 0.9.0), never locale text; the install is fail-closed (checksum mismatch/source checkout/missing checksum refuse, target untouched). | `tests/test_principles_security.py::TestPPostel`; `tests/test_utils/test_updates.py` | P-FAILFAST |
| **P-HYRUM** | Hyrum's law | Observable behaviour is someone's dependency: the API responses and their declared models are characterised before they change. | `tests/test_principles_ops.py::TestPHyrum` (46-route `METHOD /path -> response model` snapshot from `app.openapi()`; every `/api` route declares a shape except the two SSE routes, which are named with their event vocabulary); `tests/test_api` contract tests | P-YAGNI |

## D. Testing and quality

| ID | Name | Here | Bound by | Brake |
|---|---|---|---|---|
| **P-PYRAMID** | Test pyramid | Many unit tests, fewer integration, fewest end-to-end. | `tests/test_principles_testing.py` (classifies test modules and asserts floors/ceilings; prints the ratio) | P-GOODHART |
| **P-HERMETIC** | Hermetic tests | No test depends on the network, the clock, the order or the machine: the profile is redirected, host processes are hidden, and a non-loopback connection fails the test. | `tests/conftest.py` (`_isolated_profile`, `_no_host_processes`, the audit-hook guard) + `tests/test_principles_testing.py`; `tests/test_user_paths.py`; frontend MSW handlers | P-PYRAMID |
| **P-BEHAVIOR** | Test behaviour | Tests assert what the outside sees, not the inside: no assertions on private-function call counts, no patch pile-ups. | `tests/test_principles_testing.py` (private-call assertions and per-test patch caps, shrink-only) | P-GOODHART |
| **P-RISKTEST** | Risk-based testing | Effort follows risk: identity, destructive writes and data deletion are tested first. The critical modules have per-module coverage floors. | `scripts/risk_coverage.py` (per-critical-module floors, run after pytest in `scripts/quality.sh`); `tests/test_principles_testing.py` (the critical-module → test-file table) | — (brake) |
| **P-MUTATION** | Mutation testing | A test that kills no mutant is unnecessary. The pure critical modules are mutated and the score floor is enforced. | `scripts/mutation.sh` (mutmut 2.4.4 on `settings/applicability.py` and `settings/bulk_plan.py`; Windows-native by construction — 3.x refuses Windows and WSL is not a dependency of a Windows-only product). Measured 2026-10-26: **87% overall** (bulk_plan 89%, applicability 87%), floor 80 — the first run measured 50%, the gap was recorded, and the branch/message tests that closed it live in `tests/test_settings/test_applicability.py` | P-GOODHART |
| **P-GOODHART** | Goodhart's law | A measure is a diagnostic, not a target: coverage has a floor but no bonus, and no test passes without an assertion. | `tests/test_principles_testing.py` (every `test_*` contains an assertion; the coverage floor in `pyproject.toml` is documented as a floor, never raised as a goal); `pyproject.toml` coverage comment | — (brake) |
| **P-MEASURE** | Measure before optimising | Every performance change carries a before/after measurement; no gain, no change. Every number a user sees comes from an instrument on that machine. | C11's bindings: `tests/test_benchmark/test_verify_round.py` (noise floor), `tests/test_benchmark/test_sources.py` (`SOURCES`/`NO_INSTRUMENT`), `tests/test_quality_gates.py` (no summed claims); `benchmark/scheduler.py` is the only writer of a frame-rate band | — (brake) |
| **P-REPRO** | Reproducible builds | Same commit, same output: `uv.lock` and `frontend/package-lock.json` are the only dependency sources; CI installs `--locked` and `npm ci`; every `uv run --with` is pinned; the release's `pyyaml` pin must equal the `uv.lock` version. | `tests/test_principles_ops.py::TestPRepro` (lockfiles tracked, `--locked`/`npm ci`, no pip/pipx, pinned `--with`, release pin = lock version); `scripts/quality.sh` checks `npm ls` matches the lock | P-KISS |
| **P-SMALLBATCH** | Small batches | Small, single-purpose changes land often; a diff that touches unrelated subsystems is split. | `scripts/diff_budget.py` (budget for staged/branch diffs, run at pre-commit); PR template | P-KISS |
| **P-SHIFTLEFT** | One check, once, earliest | Each control runs once, at the earliest stage that can catch it, and the registry says which failure it prevents. | `scripts/controls.py` + `tests/test_principles_testing.py` (registry ↔ `quality.sh` ↔ `lefthook.yml` ↔ `ci.yml` agreement; duplicate-at-same-stage and late-only controls fail) | P-SSOT |

## E. Operations and continuity

| ID | Name | Here | Bound by | Brake |
|---|---|---|---|---|
| **P-SIGNALS** | Four golden signals | **N/A** (live users / hosted service). fpstune is one local process the user starts: no deployment, no alerting channel, no telemetry exporter (`_NO_TELEMETRY` turns tracing/metrics/logs/operation spans off; no metrics or alert SDK in `pyproject.toml`). What stands in locally is diagnostic, not alerting: `/health` readiness, the support log's one line per operation with a classified cause, `/api/self-check`, the in-memory activity journal. | Evidence: `api/main.py` (`_NO_TELEMETRY`), `api/routes/health.py`, `utils/self_check.py`, `utils/operation_log.py` | P-ERRBUDGET |
| **P-ERRBUDGET** | Error budget | **N/A**: no SLO, no users to page, no replica target. A failure is per-row and immediately visible (`ApplyResponse.success`/`verified`, the support-log line and its next step); an error budget would bound work on a service that does not exist. | Evidence: `operation_log` reason classes and hints; `tests/test_api` apply/verify contracts | — (brake) |
| **P-RPORTO** | RPO / RTO | **N/A**: there is no data store. Durable local artefacts are the support log (5 rotated files), the bench ledger (`~/.fpstune/bench`), `headroom.json` (one flat object overwritten in place) and the last-seen OS build — none is an input to correctness, every value shown is re-detected from the machine, and start-up deletes retired state files. C6 makes "acceptable loss" structural: no previous values, no history on disk. | Evidence: C6; `benchmark/ledger.py`; `operation_log._MAX_BACKUPS`; `api/main.py`'s retired-file cleanup | P-PARETO |
| **P-321** | 3-2-1 backup | **N/A** for the same absence: nothing to back up, nothing to restore. Retention exists where the catalogue's concern lands locally: support log keeps five rotated files, the opt-in debug log rotates, the activity journal is memory-only. A restore rehearsal has no subject; making it apply would require a stored history, which is a C6 red line. | Evidence: `utils/operation_log.py`, `utils/debug.py`, C6 | P-RPORTO |
| **P-WCAG** | Accessibility | Perceivable, operable, understandable, robust: labels, roles, focus traps, live regions, and errors stated in text, not only colour. | `frontend/e2e` Playwright axe run (WCAG 2.1 AA) in CI; `frontend/eslint.config.js` `eslint-plugin-jsx-a11y`; `vitest-axe` assertions in `frontend/src/**/__tests__`; `ui/ConfirmDialog` focus trap and `ui/NotificationToasts` live regions | P-TIMEBOX |

## F. Decision and effort brakes

The catalogue's section F is about how work is chosen, not about code, so its
bindings live in the work queue and the review template rather than in a test.

| ID | Name | Here | Bound by |
|---|---|---|---|
| **P-TIMEBOX** | Timebox | Work has a timebox before it starts; when it overruns, scope shrinks — the time does not grow. | `tasks.md` carries `timebox:` per open item; the audit epic (#108) and its sub-issues are the queue |
| **P-PARETO** | Pareto and diminishing returns | The few items carrying most of the value go first; the audit's first ten findings are the format, not all two hundred. | `tasks.md` priority order (P0/P1); the catalogue's own measure (probability × impact vs. effort) is stated in this document's introduction |
| **P-BIKESHED** | Bikeshedding | Disproportionate time on a trivial topic is refused: a naming debate that costs an hour is one line in review. | Judgment — review question: "does this change a failure mode?" |
| **P-PARALYSIS** | Analysis paralysis | When there is enough information to decide, decide; a spike's done-criterion is a recorded decision, not a new research list. | `tasks.md` decisions (e.g. #113 deferred by the owner; the log retention decision); owner decisions are recorded in `CLAUDE.md`/`tasks.md` |
| **P-LRM** | Last responsible moment | An irreversible decision waits for the information it needs — and no longer. Deferral carries a condition (`defer.after`) or a date. | `tasks.md` `defer.after:` field; the owner-deferred items name their condition |

---

## G. The tensions, resolved here

| Tension | Catalogue rule | How this repository applies it |
|---|---|---|
| P-DRY ↔ P-RULE3 | A copy is accepted until the third real repetition | `tests/test_principles_single_source.py` lists only concepts the project has already declared single-homed; `.jscpd.json` measures the rest without forcing an abstraction |
| P-POSTEL ↔ P-FAILFAST | FAILFAST at the inner boundary; POSTEL at the outer protocol | FastAPI/Pydantic validates every request (fail fast); `utils/updates.py` tolerates unknown/missing fields from GitHub (Postel) and classifies failures rather than raising into the UI |
| P-DELETE ↔ P-CHESTERTON | Write the reason before deleting | `settings/retired.py` + `tests/test_settings/test_retired.py`: every removed id has an entry saying what became of it (guard, replacement, no-op by limit, mitigation) |
| P-LRM ↔ P-PARALYSIS | Deferral has a condition | `tasks.md` records the condition (`defer.after`) next to each deferred item |
| P-DEPTH ↔ P-SHIFTLEFT | Depth wins for personal data and payment; elsewhere one control | There is no personal-data or payment surface, so one control per failure is the rule; the destructive write path still has lock + restore + verify because C6 makes it irreversible |

## H. Definitions without a primary source

The catalogue's section H lists eight principles whose textbook definition could
not be sourced (P-BOYSCOUT, P-POLA, P-CHESTERTON, P-FCIS, P-GOLDPLATE,
P-RISKTEST, P-PRIVACY, P-321). Their operational meaning is the catalogue's own,
and this document uses exactly that meaning: no external source is required, and
none is cited here that the catalogue did not cite.

---

## Tool substitutions and gaps

The catalogue names an audit tool per principle. Where this repository does not
use that exact tool, the substitute and its reason are here — a silent
substitution is the kind of gap this document exists to prevent.

| Catalogue tool | What ships instead | Why |
|---|---|---|
| mutmut 3.x (P-MUTATION) | mutmut **2.4.4** | 3.x refuses native Windows ("please use the WSL"); this product ships to Windows 11 only, so its gates must run on Windows. 2.4.4 is the last Windows-native release, pinned in the dev extra |
| semgrep (P-DEMETER) | the AST chain-depth check in `tests/test_principles_code.py` | one rule does not justify a second heavyweight binary to install and version; the project already parses its own AST for the section-A tests, so the rule is one test with no new dependency (P-KISS) |
| jscpd (P-DRY) | jscpd **4.x**, pinned in `frontend/package.json` | 5.x ships a Rust prebuilt binary that cannot read this workspace on Windows (it reports every path as missing); 4.x is the same tool's JavaScript line and reads it. The threshold is unchanged |
| gitleaks at pre-commit (P-SECRETS) | the dependency-free scan in `tests/test_principles_security.py` at pre-commit; real gitleaks in CI | a contributor must not need a non-project binary to commit. CI runs the real scanner over the full history as the gate of record |
| Stryker (P-MUTATION, frontend) | — (recorded gap) | the two modules whose logic carries irreversible-claim risk are Python; no frontend module has comparable weight today. If one gains it, Stryker lands with that change (C10's symmetry rule) |
| depguard (Go) | — | the project has no Go code; dependency-cruiser covers the TS side and import-linter the Python side |

## What runs where

The control registry is `scripts/controls.py`: one entry per control with its
command, the stage it runs at, and the failure it prevents. `scripts/quality.sh`
(the pre-push gate and CI's contract), `lefthook.yml` (pre-commit/pre-push) and
`.github/workflows/ci.yml` are checked against it, so a control cannot quietly
exist in only one place or run twice at the same stage.

| Stage | What runs |
|---|---|
| pre-commit (seconds) | ruff lint + format, ESLint, the tests selected by the staged files, the dependency-free secret scan, the diff budget, the control-registry check |
| pre-push / local gate | `scripts/quality.sh`: ruff, format, mypy, `lint-imports`, `vulture`, `zizmor`, the control-registry check, pytest with the coverage floor and a coverage JSON, the critical-module floors, the wall-clock (`timing`) tests serially, frontend lint/tsc/knip/dependency-cruiser/jscpd/vitest |
| CI (on demand) | the same contract on Windows + Linux, plus the real gitleaks scan, the axe browser run (colour contrast needs computed styles) and packaging |
| manual | `scripts/mutation.sh` (Windows-native), the apply sweep (#114), hardware-specific runs |

## How to run the bindings

```bash
# the whole local contract
bash scripts/quality.sh

# the individual gates this catalogue added
uv run --extra dev lint-imports
uv run --extra dev vulture src/fpstune vulture_whitelist.py --min-confidence 80
uv run --extra dev zizmor .github/workflows
uv run --extra dev python scripts/controls.py --check
uv run --extra dev python scripts/diff_budget.py --staged
uv run --extra dev python scripts/risk_coverage.py --json coverage.json
cd frontend && npm run lint && npm run knip && npm run deps:check
cd .. && frontend/node_modules/.bin/jscpd --config .jscpd.json src/fpstune frontend/src
```

## Maintenance

* A binding that stops matching its baseline fails the stale check; that is the
  point, not an inconvenience. Shrink the baseline or fix the code.
* A new principle binding needs three things: the failure it catches, the
  command that catches it, and the stage it runs at (added to
  `scripts/controls.py`).
* This document is the map, not the contract: when it and a test disagree, the
  test is right and this document is out of date.
