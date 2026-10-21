# Apply → detect → restore sweep

The harness is `tests/test_windows_contract/test_apply_roundtrip.py`. It applies
each eligible setting at its recommended value, reads it back, restores the
value it found, and reads it back again. A setting whose current value cannot be
written back is skipped, because a sweep that cannot undo itself has changed the
machine.

It mutates the machine and is therefore opt-in:

```powershell
# No writes. Prints every selected row and every skip reason.
$env:FPSTUNE_APPLY_SWEEP = "dry-run"
uv run --extra dev pytest tests/test_windows_contract/test_apply_roundtrip.py -q -s

# Real roundtrip. ELEVATED, on a disposable Windows 11 VM or with consent.
$env:FPSTUNE_APPLY_SWEEP = "all"
uv run --extra dev pytest tests/test_windows_contract/test_apply_roundtrip.py -v -s
```

`FPSTUNE_APPLY_SWEEP` also accepts ids or module names (`visual`, `timer:hpet`).
`FPSTUNE_APPLY_SWEEP_DRY_RUN=1` is the older spelling of the same dry run.

## Local matrix — 2026-10-21

Machine: Windows 11, 475 detected settings. This is an eligibility matrix plus
representative real roundtrips, not the full VM sweep.

| Result | Count |
|---|---:|
| Registered settings | 475 |
| Eligible under the harness rules | 7 |
| Skipped with a reason | 468 |

Skip reasons (broad classes; the dry run prints one line per row):

| Reason | Count |
|---|---:|
| Already at the recommended value | 354 |
| Action (runs, no state to compare) | 39 |
| Not applicable to this hardware (AMD/Intel GPU or CPU, VRR, battery, UCPD, admin) | 24 |
| Absent reading (`not_supported`, `not_installed`, `not_available`, `already_at_hardware_default`) | 36 |
| Advisory (read-only) | 10 |
| One-way PowerShell apply | 1 |
| Nothing detected | 4 |

Real roundtrips, all seven eligible rows, each first put at its default so the
apply proves a write:

| Setting | Original | Target | Observed | Restored | Agrees | Final |
|---|---|---|---|---|---|---|
| `gpu-nvidia:aniso_sample_opt` | off | on | on | off | yes | on |
| `gpu-nvidia:fps_limit` | 0 | 275 | 275 | 0 | yes | 275 |
| `gpu-nvidia:low_latency` | off | on | on | off | yes | on |
| `gpu-nvidia:texture_lod_bias` | allow | clamp | clamp | allow | yes | clamp |
| `gpu-nvidia:vrr_mode` | fullscreen | on | on | fullscreen | yes | on |
| `gpu-nvidia:vsync` | app | on | on | app | yes | on |
| `system:reserved_storage` | enabled | disabled | enabled | enabled | **no** | enabled |
| `visual:animations` | enabled | disabled | disabled | enabled | yes | disabled |
| `visual:transparency` | enabled | disabled | disabled | enabled | yes | disabled |

The one `agrees=False` row, `system:reserved_storage`, failed because Windows
returned "the requested operation requires elevation"; it was restored
unchanged (`enabled`) and is the only row still needing an elevated retry.
Every other eligible row applied, was read back, restored its original and was
left at the recommended value.

The dry run found two harness defects that the test-only rules had hidden: a
`not_supported` reading was treated as a writable value, and a hardware
condition (AMD GPU/CPU, VRR, battery, UCPD) was never consulted. Both are now
skip reasons; the dry run went from 20 to **7** eligible rows — six NVIDIA DRS
values and Reserved Storage.

## Release checklist

A release is not shippable until:

- [ ] the full elevated sweep matrix for the release commit is attached to
      #114 (owner machine with a restore point, or a disposable Windows 11 VM),
      and every `agrees=False` row is fixed or has a recorded reason;
- [ ] the Defender false-positive check (#111) has been done on the one-file
      build, with the code-signing result;
- [ ] `uv run --extra dev pytest` and the frontend gates are green on that
      commit;
- [ ] the sweep itself stays outside CI: it writes to the machine and may
      restart adapters.

## What it proves, and what it does not

It proves the write lands and the restore lands for every exercised row, and a
fake success-without-write row in
`test_a_success_without_a_visible_write_is_a_mismatch` proves the harness can
catch that class. It does not prove a row that was skipped for being already at
its recommended value; a clean skip is not a pass.
