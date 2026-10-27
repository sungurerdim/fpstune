# STATUS

Hand-written. Last update: 2026-10-27. Plan: #125. Current phase: F1, #127.

## What works

- Old tree (`src/`, `frontend/`, `tests/`): unchanged in behaviour; the full gate
  `scripts/quality.sh` passed on pre-push at 8bc702c (710 s, 2026-10-27).
- New tree, F1 units landed: schema (`schema/tweak.schema.json`), Catalogue, Detect,
  Summary, Apply, Journal, the language-neutral gate (`runtime/gate.ps1`), the bootstrap
  (`runtime/run.ps1`) and the deterministic bundle builder (`runtime/tools/build.ps1`).
- Runtime suites under tr-TR, measured 2026-10-27 with `runtime/test.ps1 -Culture tr-TR`:
  Runner 3, Schema 27, Detect 46, Summary 32, Apply 34, Bootstrap 12 passed; Failed 0 each.
- `runtime/gate.ps1` exits 0 on the current catalogue.

## What is broken or open

- `runtime/tests/Gates.Tests.ps1`: 105 passed, 35 red by design. The tests for rules LN4
  (case-sensitive operators) and FS1 (no file write, by method name too) landed before
  the rules; `gate.ps1` does not implement them yet.
- Open F1 units: U3b, U6b, U7r, U5r, U8-U12 and A1 (verify lines in #127).
- No live round-trip has run: the host has no Windows Sandbox yet (D-19 in DECISIONS.md).
- Commit 3e5e2cd carries Apply/Journal files under a test-author's message (a parallel
  commit swept them in); the content is correct, the message is not.
- The record generator (`~/.agents/araclar/kayit-uret.py`) does not support this repo
  yet; TODO.md and ARCHIVE.md were generated from `gh issue list` by a one-off script.

## Live configuration

- Host: Windows 11 Pro, tr-TR. Windows PowerShell 5.1 is the runtime engine.
- Pester 5.9.1, pinned with its SHA-512 in `runtime/tools/pester.pin.ps1`, restored into
  the git-ignored `runtime/.modules/`.
- lefthook 2.1.12: pre-commit runs ruff check --fix, ruff format and eslint --fix on
  staged files with `stage_fixed`; pre-push runs `scripts/quality.sh` check-only.
- `scripts/quality.sh` exports `PYTHONUTF8=1` (lint-imports failed under cp1254).
- `scripts/controls.py` registers 28 controls.
