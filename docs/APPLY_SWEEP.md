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

Representative real roundtrips (same `_roundtrip` path, non-elevated HKCU):

| Setting | Original | Applied | Restored | Agrees | Final |
|---|---|---|---|---|---|
| `visual:animations` | enabled | disabled | enabled | yes | disabled |
| `visual:transparency` | enabled | disabled | enabled | yes | disabled |

The dry run found two harness defects that the test-only rules had hidden: a
`not_supported` reading was treated as a writable value, and a hardware
condition (AMD GPU/CPU, VRR, battery, UCPD) was never consulted. Both are now
skip reasons; the dry run went from 20 to **7** eligible rows — six NVIDIA DRS
values and Reserved Storage. They need administrator rights.

The elevated full sweep was launched, but UAC was cancelled, so no write ran.
The two HKCU rows above remain the real-roundtrip evidence; the full elevated
matrix is still required for #114.

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
