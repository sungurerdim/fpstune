# STATUS

Hand-written. Last update: 2026-10-28. Plan: #125, phases F1-F7 as sub-issues
#127-#133. Current phase: F1, #127.

## What works

- Old tree (`src/`, `frontend/`, `tests/`): frozen by D-21, no further fixes; the full
  gate `scripts/quality.sh` passed on pre-push at 8bc702c (710 s, 2026-10-27).
- New tree, F1 units landed: schema, Catalogue, Detect, Summary, Apply, Journal, the
  language-neutral gate with LN4 and FS1 (`runtime/gate.ps1`), the bootstrap
  (`runtime/run.ps1`, U7r findings fixed) and the bundle builder (`runtime/tools/build.ps1`).
- 10 tweaks in `tweaks/` (U8-U10); `runtime/gate.ps1` exits 0 on them (2026-10-28).
- Runtime suites under tr-TR, measured 2026-10-28: Gates 154, Apply 37, Bootstrap 30
  passed; Failed 0 each.

## What is broken or open

- `start.bat` double-click opens no window; not fixed by decision D-21.
- Open F1 units: U4b, U5b, U6c, U11, U12 and A1 (verify lines in #127).
- No live round-trip has run: Windows Sandbox is enabled but waits for a reboot
  (package state 96 = install pending, measured 2026-10-28; D-19).
- Rows that need a native API (NVIDIA DRS, DisplayConfig, wlanapi) go through an
  in-memory Emit invoker (D-24); not built yet (#129 U1), and not yet proven under
  `irm | iex` with Defender on.
- Commit 3e5e2cd carries Apply/Journal files under a test-author's message (a parallel
  commit swept them in); the content is correct, the message is not.
- The record generator (`~/.agents/araclar/kayit-uret.py`) does not support this repo
  yet; TODO.md and ARCHIVE.md were generated from `gh issue list` by a one-off script.
- Open issue #81 predates the issue template; edit it with the issue tool only after
  bringing its body to the template.

## Live configuration

- Host: Windows 11 Pro, tr-TR. Windows PowerShell 5.1 is the runtime engine.
- Pester 5.9.1, pinned with its SHA-512 in `runtime/tools/pester.pin.ps1`, restored into
  the git-ignored `runtime/.modules/`.
- lefthook 2.1.12: pre-commit runs ruff check --fix, ruff format and eslint --fix on
  staged files with `stage_fixed`; pre-push runs `scripts/quality.sh` check-only.
- `scripts/quality.sh` exports `PYTHONUTF8=1` (lint-imports failed under cp1254).
- `scripts/controls.py` registers 28 controls.
