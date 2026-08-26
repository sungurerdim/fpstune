# File-Split Refactor Plan

The larger structural refactors, kept out of PRs that carry surgical fixes:
each split touches imports across the codebase and deserves focused review.
Entries describe the extraction *shape* — module boundaries and exported
symbols — and deliberately carry no line numbers or line counts. Both went
stale between every two commits in earlier revisions of this document;
re-measure before quoting a size.

## Status, verified against the tree 2026-08-25

**Done, and removed from the plan below:**

- `api/routes/system.py` — split into `system.py` plus `system_network.py`,
  `system_audio.py` and `system_power.py`, each with its own router, over the
  shared `system_common.py`. The detail-detection helpers went further out:
  `system_hardware.py` is gone and its contents now live in the `api/hardware/`
  package (`network_adapters.py`, `storage.py`, `audio.py`), which carries no
  router.
- `api/routes/settings.py` SSE half — moved to `settings_stream.py`.
- `executors/powershell.py` — the `ACTION_COMMANDS` table now lives in
  `executors/powershell_actions.py`; `PowerShellExecutor` stays behind.
- `components/HardwarePanel.tsx` — now a composition shell over the
  `frontend/src/components/hardware/` package (`MonitorCard`,
  `NetworkAdapterCard`, `StorageDriveCard`, `AudioSection`, `DeviceTweakList`).
- `frontend/src/store/settings.ts` — shrank below the size that put it here.

**Still open:** everything below.

---

## Split `settings/definitions/system.py`

The file already groups its content into named sub-lists — `MEMORY_SETTINGS`,
`SERVICES_SETTINGS`, `SYSTEM_CONFIG_SETTINGS`, `PRIVACY_SETTINGS`,
`PERFORMANCE_SETTINGS`, `CLEANUP_SETTINGS`, `MAINTENANCE_SETTINGS` — so the
split is mechanical: one sibling module per sub-list
(`definitions/system_memory.py`, `definitions/system_services.py`, …), and
`system.py` becomes a thin aggregator that re-exports `SYSTEM_SETTINGS` as the
concatenation. Only `definitions/__init__.py` imports `SYSTEM_SETTINGS`, so
the public API does not move.

## Split `settings/definitions/network.py`

Same shape. Suggested groups:

- `network_tcp.py` — TCP/IP global settings
- `network_dns.py` — DNS provider configuration
- `network_adapter.py` — per-adapter properties and their factories
- `network_throttling.py` — QoS and throttling

Caveat: `settings/registry.py` imports specific symbols from `network.py`
(the per-adapter factories and `create_mtu_setting`). Those imports must be
re-pointed at the new submodules.

## Split `core/nv_profile.py`

Largest single class. Boundaries:

- `nv_profile_download.py` — Profile Inspector binary download + cache
- `nv_profile_xml.py` — profile XML generation
- `nv_profile_apply.py` — subprocess invocation
- `nv_profile.py` — facade `NvidiaProfileInspector` composing the above

## Split `utils/detect.py` and `settings/definitions/gpu.py`

- `detect.py` already has internal sections; split into `detect_gpu.py`,
  `detect_cpu.py`, `detect_monitors.py`, `detect_os.py` with a thin
  re-exporting aggregator so callers don't change.
- `definitions/gpu.py` — split into `gpu_nvidia.py`, `gpu_amd.py`,
  `gpu_intel.py`.

## Split `frontend/src/lib/api.ts`

One module per resource: `api/settings.ts`, `api/system.ts`,
`api/benchmark.ts`, `api/safety.ts`, re-exported from `api.ts` so existing
`import { ... } from './lib/api'` call sites keep working during a
deprecation window.

## Smaller tightening

| File | Action |
|------|--------|
| `api/routes/settings.py` | Extract the long non-SSE helpers; the SSE half is already out |
| `commands/benchmark.py` | Extract each bench subcommand tree into its own module |
| `benchmark/presentmon.py` | Split the capture lifecycle from the CSV parser |
| `settings/base.py` | Move the enums to `enums.py`; `SettingExecutor` stays |
| `frontend/src/types/setting.ts` | Split into `types/setting.ts` (core) plus category types |

---

## Sequencing recommendation

1. **PR #1** — split `definitions/system.py`. Lowest risk: only the
   aggregator is imported externally.
2. **PR #2** — split `core/nv_profile.py`. Self-contained.
3. **PR #3+** — remaining splits (network, gpu, detect, api.ts) one per PR.

After every split, run `pytest tests/ --no-cov` to confirm the registry still
discovers the same number of `SettingExecutor` instances and no import errors
leak.
