# Cleanup commands: what is measured, what is claimed

The cleanup surface has one rule: a row may show bytes only when an instrument
measured them, and the number must mean what the action can actually remove
(C11). This file records the audit behind the current behaviour.

## Component store (DISM)

Sources:

- [Clean Up the WinSxS Folder](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/clean-up-the-winsxs-folder)
- [Determine the Actual Size of the WinSxS Folder](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/determine-the-actual-size-of-the-winsxs-folder)

Microsoft splits the store into *Actual Size*, *Backups and Disabled Features*
and *Cache and Temporary Data*. The cleanup opportunity is **not** the whole
overhead:

- `Number of Reclaimable Packages` and `Component Store Cleanup Recommended`
  say whether a cleanup is entitled to remove anything.
- `/ResetBase` makes installed updates permanent; fpstune offers it, never
  recommends it.
- A reboot can be required before the reclaimed space is visible.

Behaviour now: `Get-DismReclaimableMB` reads both fields. With no reclaimable
package and no recommendation it reports `0 MB (nothing reclaimable)`; otherwise
the number is labelled `(DISM estimate)`, and the row is called an estimate. It
is no longer presented as a promise of GB.

## Temp and path cleanups

- The walk and the delete use the same `resolved_paths` list, so a folder is
  never counted but left, or deleted but never counted.
- The walk skips reparse points; errors stay local to one subtree.
- Top-level directories are measured in parallel (up to eight workers). Temp
  can hold hundreds of top-level entries and hundreds of thousands of files;
  the serial walk was filesystem-latency bound.
- **The displayed size is a candidate, not a promise.** Files another process
  holds open survive `Remove-Item`, and Windows may round/compress allocation.
  The freed figure is a *before/after pair* with the same instrument, so it
  reports what actually vanished, not the candidate.
- `keep_recent_hours` and `keep_names` use the same top-level filter for the
  size and the delete.

## Docker and WSL

- `docker system prune -f` removes stopped containers, dangling images and
  build cache — not unused tagged images or volumes.
- `docker system prune -a -f` adds all unused images; named volumes stay.
- The VHDX is compacted after the prune (`wsl --manage --set-sparse true`,
  with `diskpart compact vdisk` as fallback).
- `docker_prune`, `docker_prune_all` and `wsl_compact` reclaim **overlapping**
  storage. The group header now shows the largest alternative, not their sum
  (8.7 + 12.7 GB was shown as 20.9 GB).

## Open items

- `cleanup:prefetch`: Windows manages Prefetch itself; deleting it is widely
  reported to slow first launches. It is small (1 MB here) and should be
  retired or made advisory in a follow-up, with a source.
- Browser/vendor cache commands were not independently re-sourced in this
  pass; their path lists and delete filters are shared with the measured walk.
- `freed_bytes` is logical bytes from the same walk; it does not yet use
  allocated (`GetCompressedFileSize`) bytes or deduplicate hard links.
