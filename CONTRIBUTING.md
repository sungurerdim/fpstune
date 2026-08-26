# Contributing to fpstune

## Prerequisites

- **Python 3.12+** with pip — the floor is whatever CI runs and nothing wider;
  the backend suite runs on 3.12 and 3.13 on every push, and the release is
  built on 3.12
- **Node.js 20+** with npm
- **Windows 11** (recommended for full testing; Linux/macOS works for unit tests)
- **Administrator privileges** (for integration tests that touch registry/services)

## Setup

```bash
# Clone
git clone https://github.com/sungurerdim/fpstune.git
cd fpstune

# Python backend
pip install -e ".[dev]"

# Frontend
cd frontend && npm install && cd ..

# Verify
pytest tests/ -x --tb=short
cd frontend && npm run lint && npx tsc --noEmit
```

## Running Locally

```bash
# Backend (terminal 1)
uvicorn fpstune.api.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend (terminal 2)
cd frontend && npm run dev
```

Open http://localhost:5173. The frontend proxies API requests to port 8000.

## Project Structure

| Path | Role |
|------|------|
| `src/fpstune/api/routes/` | FastAPI route handlers |
| `src/fpstune/settings/definitions/` | SettingExecutor instances (one file per category) |
| `src/fpstune/settings/executors/` | Registry, PowerShell, Netsh, POWERCFG executors |
| `src/fpstune/core/` | System integrations (BcdEdit, DISM, NV Inspector) |
| `src/fpstune/safety/` | System Restore point creation and listing |
| `src/fpstune/utils/` | Hardware detection, admin check, PowerShell runner |
| `frontend/src/components/` | React components |
| `frontend/src/lib/` | API client, detection manager, structured logger |
| `tests/` | Pytest test suite |

## Adding a New Setting

1. Create a `SettingExecutor` instance in the appropriate `src/fpstune/settings/definitions/<category>.py` file
2. Add it to the module's `_SETTINGS` list at the bottom of the file
3. Every setting must have:
   - `impact_scores` with at least one numeric metric (e.g., `{"fps": "+3-5%"}`)
   - `description` ending with a period (1-2 sentences)
   - `current_impact` and `recommended_impact` in `"State: Consequence"` format
4. Run `pytest tests/ -x` to verify no regressions

See `CLAUDE.md` for the 11 enforced quality gates (C1-C11); `docs/ARCHITECTURE.md` lists them in short form.

## Testing

```bash
# Run all tests
pytest tests/ -x --tb=short

# Run with coverage
pytest tests/ --cov=src/fpstune --cov-report=term-missing

# Run specific test file
pytest tests/test_settings/test_applicability.py -v

# Frontend lint + typecheck
cd frontend && npm run lint && npx tsc --noEmit
```

Tests use `unittest.mock` to mock Windows-specific calls (registry, PowerShell, subprocess). The `conftest.py` provides fixtures for common mocks.

**Coverage is a gate, not a dashboard.** `pyproject.toml` sets `fail_under = 70`,
so `pytest --cov` exits non-zero below that and CI's backend job fails with it.
The number is a floor under what already passes rather than a target to chase —
it moves up when real coverage has moved up, never ahead of it, because a gate
set above the truth gets lowered the first time it is inconvenient.

## Dependency Updates and Lockfiles

Two lockfiles decide what everything here is built against: `uv.lock` for Python
and `frontend/package-lock.json` for the React tree. Both are watched by
Dependabot (`.github/dependabot.yml`), on a schedule chosen so a solo maintainer
does not turn it off:

| Ecosystem | Where | When | Batched as |
|-----------|-------|------|------------|
| `uv` | `/` | weekly, Monday 06:00 UTC | one PR for all minor + patch |
| `npm` | `/frontend` | weekly, Monday 06:00 UTC | one PR for all minor + patch |
| `github-actions` | `/` | monthly | one PR for all minor + patch |

Majors are deliberately left ungrouped — those are the ones that need reading, so
each arrives on its own.

`requirements.txt` is **generated**, not edited: `task lock` runs `uv lock` and
then exports it from the lock. Because that export is committed by hand, the two
can disagree and nothing would notice — `uv sync --frozen` only proves the lock
matches `pyproject.toml`. CI's `lockfiles` job closes that: it re-runs the export
byte-for-byte and fails on any diff, so anyone installing from `requirements.txt`
gets the dependency set every other check ran against. `task lock-check`
reproduces it locally.

Expect Dependabot's own Python PRs to trip that job: it updates `uv.lock` without
re-exporting. `task lock` on the branch is the fix, and the failure message says
so.

## Code Standards

- **Python**: ruff for linting + formatting, mypy for type checking (strict mode)
- **Frontend**: ESLint with `no-console` rule (use `createLogger` from `lib/logger.ts`), TypeScript strict
- **Commits**: Conventional commits required (`feat:`, `fix:`, `refactor:`, etc.); a lefthook `commit-msg` hook rejects anything else
- **Pre-commit**: lefthook runs the *full* checks, not just the staged files — staging any `.py` file triggers `ruff check src tests`, `ruff format --check src tests`, `mypy src` and the whole pytest suite (`--no-cov -x`); staging anything under `frontend/` triggers ESLint, `tsc --noEmit` and the vitest suite. The commands run in parallel, but expect a Python commit to take as long as the test suite does — that is the point, not an accident

## Repo Scripts

What `scripts/` holds, so nobody has to reverse-engineer it:

| Script | What it does |
|--------|--------------|
| `dev_setup.py` | One-shot dev environment: Python deps + `npm install` |
| `build_exe.py` | Single-file PyInstaller exe (expects `frontend/dist` to exist) |
| `build_all.py` | Frontend build + tests + exe + staged release folder |
| `sync_version.py` | Copies the `pyproject.toml` version into `__init__.py` and `package.json`; `tests/test_release_contract.py` fails when a copy drifts |
| `update_winget_manifest.py` | Points the `winget/` manifests at a built exe: rewrites version, download URL, `ReleaseDate` and checksum from that binary's own bytes. The release workflow runs it against the exe it just built, checks the manifest parses as YAML and carries that exe's checksum, and uploads the result as a `winget-manifest` artifact; `task winget` runs the same script locally |
| `measure_scan.py` | Before/after cost measurement for detection-pipeline changes; internal tooling |

`winget/` holds the manifest template that script fills in. Until a release is
published and the script has run, the checked-in manifest is a template with a
zeroed checksum, not something submittable to winget-pkgs.

**Submitting to winget-pkgs is a deliberate human step, and no workflow does
it.** Nothing in `.github/workflows/` pushes to any repository other than this
one, opens a pull request against `microsoft/winget-pkgs`, or holds a token that
could. Automating it would mean storing write access to a fork of a third-party
repository in a public repo whose whole threat model is "this binary asks for
Administrator" — and it would buy nothing, because the binary is unsigned and
every submission of an unsigned package goes to human moderation anyway. What is
automated is the part a person gets wrong by hand: the version, the URL, the
date and above all the checksum. Download the `winget-manifest` artifact, run
`winget validate` on it, commit it back here, then open the pull request
yourself.

`start.bat` / `start.ps1` at the repo root self-elevate and launch the UI from
a source checkout — the source-tree equivalent of double-clicking the exe.

## Pull Request Process

1. Create a branch from `main`
2. Make your changes (see code standards above)
3. Run `pytest tests/ -x` and `ruff check src/`
4. Write a clear PR description explaining what and why
5. CI runs automatically on push, in three jobs: `backend` (ruff, mypy and the
   coverage-gated pytest suite, once per Python version in the matrix),
   `lockfiles` (`requirements.txt` still matches `uv.lock`), and `frontend`
   (type-check + build, ESLint, vitest)

## Key Conventions

- **English only** in all code, comments, and docs
- Each `SettingExecutor` modifies exactly 1 logical setting
- Async route handlers must wrap blocking subprocess calls with `asyncio.to_thread()`
- Hardware detection results are cached (see `utils/detect.py` and `hardware_manager.py`)
- Frontend logging uses `createLogger('Scope')` — never bare `console.*`
