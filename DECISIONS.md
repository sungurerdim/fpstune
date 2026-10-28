# DECISIONS

One line per decision: `D-<n> · date · subject · decision · reason · superseded-by`.
Append only. A superseded line stays and gains `superseded by D-<n>`.
The F1 design decisions D1-D7 live in the body of #127; D-20 below points to them.

- D-1 · 2026-10-27 · rewrite · Replace the Python, React and exe tree with JSON tweaks and a Windows PowerShell 5.1 runtime; any breaking or stack change is allowed · settings were code, not data; reset, hardware and locale classes caused most fixes; the exe was flagged by Defender · —
- D-2 · 2026-10-27 · delivery · One line `irm ... | iex`; no exe, no file left behind; code signing optional · nothing to install or flag; the user sees the script · —
- D-3 · 2026-10-27 · tweak source · One JSON file per tweak in a category folder, with literal detect, apply and revert commands; a static site (GitHub Pages) shows the catalogue · transparency; a user can learn and reuse each command · —
- D-4 · 2026-10-27 · way back · No reset button; each tweak JSON carries a revert command; a restore point is taken before bulk apply; replaces C6 for the new tree · the reset machinery caused about 15 fixes · —
- D-5 · 2026-10-27 · numbers · No number a user sees unless an instrument measured it; otherwise one sentence names the fixed problem; C2 retired, a tweak carries gain kinds only · claimed numbers were meaningless (C11) · —
- D-6 · 2026-10-27 · measurement · No default before/after benchmark; measurement only in the doctor (about 60 s in the user's real game); the synthetic 1.3 GB scene is dropped · tool runtime stays minimal · —
- D-7 · 2026-10-27 · UI · Console first; WPF only if a later need is measured · fewest moving parts · —
- D-8 · 2026-10-27 · frame pacing · Frame cap from the panel: `min(hz-3, floor(hz - hz^2/3600))` (144 Hz → 138), with the single ideal VRR + Reflex combination · stays inside the VRR window; no wasted frames or heat · —
- D-9 · 2026-10-27 · overlays and telemetry · Steam and NVIDIA overlays untouched; telemetry and data sharing off where it has no side effect · streamers use overlays · —
- D-10 · 2026-10-27 · cleanup · Default set holds only files Windows regenerates (Temp older than 24 h, Windows Update download cache, Delivery Optimization, crash dumps); never shader caches, Recycle Bin or Downloads; low free space adds DISM component cleanup without /ResetBase · zero risk · —
- D-11 · 2026-10-27 · memory · No RAM cleaner, standby purge or ClearPageFileAtShutdown; the pagefile returns to system-managed; the doctor names the memory-heavy process · those tools cost more than they give · —
- D-12 · 2026-10-27 · audio · Loudness equalization on for speakers, off for headphones · footstep direction is information on headphones · —
- D-13 · 2026-10-27 · repairs · sfc and DISM only when the doctor proposes them, with a separate confirmation; boot-time repair is never scheduled · a chkdsk boot loop once bricked a laptop · —
- D-14 · 2026-10-27 · browsers · Background mode off through the policy key; the copy says the browser will show "managed by your organization" · stops idle browser load; the user is not surprised · —
- D-15 · 2026-10-27 · DNS · Filtered resolvers (9.9.9.9, 9.9.9.11, 1.1.1.2); a probe picks the lowest p90; DNS over HTTPS on · minimum latency with malware blocking · —
- D-16 · 2026-10-27 · aim settings · FPS games always ship aim and ADS rows; MW4 Focus (Auto) and Change Zoom Activation (Melee) live in the binary `g.cod26.*.b` with hashed keys, so they are manual rows · a hashed binary cannot be written safely · —
- D-17 · 2026-10-27 · entry point · AGENTS.md is the one entry point; CLAUDE.md holds `@AGENTS.md`; tasks.md is retired, the plan lives in #125 and #127 · an agent with no context finds everything from one file · —
- D-18 · 2026-10-27 · commit hooks · Every check with a fix mode runs it at pre-commit on staged files and re-stages (lefthook `stage_fixed`); pre-push and CI stay check-only · a fixable finding must never cost a red · —
- D-19 · 2026-10-27 · clean-machine tests · Live round-trip tests run only in Windows Sandbox or a CI runner, never on the owner's PC; the owner enables Sandbox · the owner's PC is not disposable · —
- D-20 · 2026-10-27 · F1 design · New tree beside `src/` (`tweaks/`, `schema/`, `runtime/`), schema, runtime modules, language-neutral gate, Pester 5.9.1 pinned, gates G1-G5: see #127 D1-D7 · the plan's owner is the issue · —
- D-21 · 2026-10-28 · old tree frozen · No more fixes to the Python, React and exe tree, including the start.bat double-click failure (no window opens); all effort goes to the rewrite phases F1-F6 · the old tree is deleted in F6, so a fix there is discarded work · —
