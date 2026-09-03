import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { settingsApi, type BulkApplyResponse } from "../lib/api";
import { detectionManager } from "../lib/detection-manager";
import { createLogger } from "../lib/logger";
import { useStore, type CleanupResult } from "../store";
import { parseSizeToMB } from "../lib/cleanupSize";
import type { Setting, SettingId } from "../types/setting";

const log = createLogger("CleanupRunner");

/** Modules whose actions report a reclaimable size (freed-space tracking). */
const SIZE_MODULES = new Set(["cleanup", "game_cleanup"]);

/**
 * Module-level state so a cleanup started on one tab still resolves its freed
 * space after the user navigates away, and the one-time size detection fires
 * exactly once per session regardless of which tab mounted first.
 *
 * An id is in `pendingFreed` only once the run that armed it has reported
 * success, because that is the moment the backend has invalidated its cached
 * size — see the mutation's onMutate/onSuccess pair.
 */
const pendingFreed: Record<string, { beforeMB: number; armedAt: number }> = {};
let detectTriggered = false;

type CleanupSizes = Awaited<ReturnType<typeof settingsApi.getCleanupSizes>>;

/**
 * How long a freed-space report may wait for its new size before the row is
 * closed out without one.
 *
 * Longer than any answer the backend can owe: it settles a claimed size within
 * the claiming worker's own deadline (cleanup_cache.mark_calculating), and the
 * longest of those is the batch's timeout — 30 s plus 12 s per cleanup type,
 * about five minutes for the twenty this ships. So this only ever fires when the
 * backend stopped answering at all, which is a restart mid-wait, and the row
 * then reports the cleanup as done rather than spinning on a number that is
 * never coming.
 */
const PENDING_FREED_TIMEOUT_MS = 7 * 60 * 1000;

/**
 * Report freed space for every pending run whose new size has landed, and give
 * up on any whose size never will.
 *
 * Called from both the poll's change-effect and the run itself, because the two
 * can happen in either order: a small cleanup is often re-measured before the
 * bulk request that ran it has even returned, and a resolution driven only by
 * the poll would then wait for a change that has already happened — leaving the
 * row spinning on a number that was ready all along.
 */
function resolvePendingFreed(sizes: CleanupSizes): void {
  const resolved: CleanupResult[] = [];
  const now = Date.now();
  for (const [id, pending] of Object.entries(pendingFreed)) {
    const entry = sizes[id];
    const waiting = !entry || entry.status === "calculating";
    if (waiting && now - pending.armedAt < PENDING_FREED_TIMEOUT_MS) continue;
    delete pendingFreed[id];
    const setting = useStore.getState().settings.get(id as SettingId);
    const name = setting?.displayName ?? id;
    if (!entry || entry.status !== "ready") {
      // No new size is coming — still measuring past its deadline, the service
      // is down, or the target is gone. The cleanup itself succeeded, so the row
      // says that instead of spinning on a figure nothing measured (C11 rule 3).
      resolved.push({ id, name, success: true, sized: false, freedMB: null });
      continue;
    }
    const mb = Math.round(entry.bytes / (1024 * 1024));
    resolved.push({
      id,
      name,
      success: true,
      sized: true,
      freedMB: Math.max(0, pending.beforeMB - mb),
    });
  }
  if (resolved.length > 0) useStore.getState().recordCleanupResults(resolved);
}

/** Docker prune actions restart Docker + WSL, so they need a confirm gate. */
export function isDockerCleanup(s: Setting): boolean {
  return s.name === "docker_prune" || s.name === "docker_prune_all";
}

const asText = (value: unknown): string =>
  typeof value === "string" ? value : "";

/**
 * Run the ids through the streaming endpoint, driving the live run rows, and
 * answer with the same shape the quiet bulk endpoint returned.
 *
 * The two halves are deliberately separate: the events are what the user reads
 * while it happens, the assembled result is what the freed-space bookkeeping
 * reads afterwards. Neither is derived from the other, so a change to the panel
 * cannot quietly change what counts as a successful cleanup.
 */
function runStreamed(ids: string[]): Promise<BulkApplyResponse> {
  const store = useStore.getState();
  store.beginRun(
    ids.map((id) => ({
      id,
      name: store.settings.get(id as SettingId)?.displayName ?? id,
    })),
  );

  return new Promise<BulkApplyResponse>((resolve, reject) => {
    const results: BulkApplyResponse["results"] = {};
    let requiresReboot = false;

    const finish = () => {
      const values = Object.values(results);
      resolve({
        results,
        success_count: values.filter((r) => r.success).length,
        error_count: values.filter((r) => !r.success).length,
        requires_reboot: requiresReboot,
      });
    };

    settingsApi.bulkStreamApply(
      ids,
      (event) => {
        const id = asText(event.id);
        if (!id) return;
        const { updateRunStep, appendRunOutput } = useStore.getState();

        switch (event.event) {
          case "started":
            updateRunStep(id, {
              status: "running",
              startedAt: Date.now(),
              name: asText(event.name) || undefined,
              durationEstimate: asText(event.duration_estimate),
              reportsProgress: event.reports_progress === true,
            });
            return;
          case "output": {
            const text = asText(event.text);
            // The command itself is the first line the backend sends, so the row
            // can show what is running before it has run.
            const step = useStore
              .getState()
              .runSteps.find((s) => s.id === id);
            if (step && !step.command) updateRunStep(id, { command: text });
            else appendRunOutput(id, text, event.replaces === true);
            if (typeof event.percent === "number") {
              updateRunStep(id, { percent: event.percent });
            }
            return;
          }
          case "applied":
            results[id] = {
              setting_id: id,
              success: true,
              error: null,
              new_value: event.current_value ?? null,
              requires_reboot: event.requires_reboot === true,
              skipped: false,
              // The stream reports verification in its own `verified` event and
              // the rows read it there; this shape exists for the freed-space
              // bookkeeping, which asks only whether the cleanup ran.
              verified: null,
            };
            if (event.requires_reboot === true) requiresReboot = true;
            updateRunStep(id, {
              status: "done",
              endedAt: Date.now(),
              percent: 100,
            });
            return;
          case "skipped":
            results[id] = {
              setting_id: id,
              success: true,
              error: null,
              new_value: null,
              requires_reboot: false,
              skipped: true,
              verified: null,
            };
            updateRunStep(id, { status: "skipped", endedAt: Date.now() });
            return;
          case "failed": {
            const error = asText(event.error) || "Unknown error";
            results[id] = {
              setting_id: id,
              success: false,
              error,
              new_value: null,
              requires_reboot: false,
              skipped: false,
              verified: null,
            };
            updateRunStep(id, { status: "failed", endedAt: Date.now(), error });
            return;
          }
          default:
            // "verified" and "done" carry nothing the rows do not already have.
            return;
        }
      },
      finish,
      // A stream that dies mid-run must reject rather than leave the mutation
      // pending: a promise waiting for a `done` that is never coming is a Run
      // button that stays busy for the rest of the session.
      (error) =>
        reject(error instanceof Error ? error : new Error(String(error))),
    );
  });
}

/**
 * Mounted once via <CleanupRunnerProvider/>: kicks off the one-time size
 * detection for every size-bearing cleanup, polls ["cleanup-sizes"], syncs the
 * results into the store, and resolves freed space (before − after) for any run
 * that snapshotted a pre-size. Runs regardless of the active tab.
 */
export function useCleanupSizePolling(): void {
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const setSettingDetectionResult = useStore(
    (s) => s.setSettingDetectionResult,
  );

  const sizeBearingIds = useMemo(() => {
    const ids: SettingId[] = [];
    for (const s of settings.values()) {
      if (!s.isAction || !s.isApplicable) continue;
      if (SIZE_MODULES.has(s.module)) ids.push(s.id);
    }
    return ids;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion]);

  // One-time background size calculation for all size-bearing cleanups.
  //
  // Routed through the DetectionManager rather than posting /detect here: this
  // was the fourth hand-written copy of the detect-response-to-store mapping,
  // and it carried four of the six fields — which is how the copy before it
  // came to blank `recommended_value` and `original_value` on everything it
  // touched. There is one mapping and every caller uses it.
  useEffect(() => {
    if (detectTriggered || sizeBearingIds.length === 0) return;
    detectTriggered = true;
    detectionManager.redetectSettings(sizeBearingIds).catch(() => {
      /* detection errors are non-fatal */
    });
  }, [sizeBearingIds]);

  // Track whether any size-bearing cleanup is still "calculating".
  const calculatingRef = useRef(false);
  useEffect(() => {
    calculatingRef.current = sizeBearingIds.some((id) => {
      const v = settings.get(id)?.currentValue;
      return typeof v === "string" && v.includes("calculating");
    });
  }, [sizeBearingIds, settings]);

  const { data: cleanupSizes } = useQuery({
    queryKey: ["cleanup-sizes"],
    queryFn: settingsApi.getCleanupSizes,
    refetchInterval: (query) => {
      // A run waiting for its freed-space figure keeps the poll alive on its own
      // account. Reading only the last response would stop it in the gap between
      // a cleanup being applied and its size being claimed again — and a poll
      // that stops there never delivers the number the row is spinning for.
      if (Object.keys(pendingFreed).length > 0) return 3000;
      const data = query.state.data;
      if (data && Object.values(data).some((v) => v.status === "calculating"))
        return 3000;
      if (calculatingRef.current) return 3000;
      return false;
    },
  });

  // Sync completed sizes into the store + resolve pending freed-space results.
  useEffect(() => {
    if (!cleanupSizes) return;
    for (const [id, entry] of Object.entries(cleanupSizes)) {
      if (entry.status === "not_installed") {
        // Target software/dirs absent → not applicable: hidden everywhere and
        // excluded from every total (all UI filters key off isApplicable).
        setSettingDetectionResult(
          id as SettingId,
          null,
          false,
          false,
          "Not installed on this system",
        );
        continue;
      }
      if (entry.status === "unavailable") {
        setSettingDetectionResult(
          id as SettingId,
          "ready|unavailable",
          false,
          true,
        );
        continue;
      }
      if (entry.status !== "ready") continue;
      const mb = Math.round(entry.bytes / (1024 * 1024));
      setSettingDetectionResult(id as SettingId, `ready|${mb} MB`, false, true);
    }
    resolvePendingFreed(cleanupSizes);
  }, [cleanupSizes, setSettingDetectionResult]);
}

interface UseCleanupRunnerOptions {
  /** Which action modules this runner scopes selection + run to. */
  modules: string[];
}

export interface CleanupRunner {
  selectedIds: string[];
  selectedCount: number;
  hasSelection: boolean;
  isRunning: boolean;
  /** Run the given ids (default: the current selection). Gated by a docker confirm. */
  run: (ids?: string[]) => void;
  /** Non-null while a docker-involving run awaits confirmation. */
  confirmIds: string[] | null;
  confirmRun: () => void;
  cancelConfirm: () => void;
}

/**
 * Owns cleanup/maintenance execution for a set of modules. Selection comes from
 * the shared store (maintenanceSelection); freed-space tracking is resolved by
 * <CleanupRunnerProvider/>. Docker prune runs are gated behind a confirm because
 * they restart Docker + WSL.
 */
export function useCleanupRunner({
  modules,
}: UseCleanupRunnerOptions): CleanupRunner {
  const queryClient = useQueryClient();
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const selection = useStore((s) => s.maintenanceSelection);
  const toggleMaintenanceSelection = useStore(
    (s) => s.toggleMaintenanceSelection,
  );
  const recordCleanupResults = useStore((s) => s.recordCleanupResults);
  const addNotification = useStore((s) => s.addNotification);

  const [confirmIds, setConfirmIds] = useState<string[] | null>(null);

  const moduleSet = useMemo(() => new Set(modules), [modules]);

  const actionIds = useMemo(() => {
    const ids: string[] = [];
    for (const s of settings.values()) {
      if (!s.isAction || !s.isApplicable) continue;
      if (moduleSet.has(s.module)) ids.push(s.id);
    }
    return ids;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion, moduleSet]);

  const selectedIds = useMemo(
    () => actionIds.filter((id) => selection[id]),
    [actionIds, selection],
  );

  const runMutation = useMutation({
    // Streamed rather than posted-and-waited, because the answer is not the only
    // thing worth having: a DISM repair runs for half an hour, and the events
    // are what turn that from one spinner into a row that says which command is
    // running and how far it has got. The assembled result keeps the same shape
    // the quiet endpoint returned, so everything downstream is unchanged.
    mutationFn: (ids: string[]) => runStreamed(ids),
    onSettled: (_data, _err, ids) => {
      useStore.getState().endOperation();
      // Running one docker prune changes the OTHER's reclaimable estimate; the
      // backend invalidated both sibling caches, so re-detect both docker ids to
      // recompute their now-stale sizes (the run id refreshes on its own path).
      const ranDocker = ids?.some((id) => {
        const s = settings.get(id as SettingId);
        return s && isDockerCleanup(s);
      });
      if (ranDocker) {
        const dockerIds: string[] = [];
        for (const s of settings.values()) {
          if (isDockerCleanup(s) && s.isApplicable) dockerIds.push(s.id);
        }
        if (dockerIds.length > 0) {
          detectionManager.redetectSettings(dockerIds).catch(() => {});
        }
      }
    },
    onMutate: (ids: string[]) => {
      // The store's busy flag, so the hardware re-read on window focus stays off
      // the machine while a cleanup holds PowerShell. A DISM run takes minutes.
      useStore.getState().beginOperation();
      // Snapshot pre-cleanup sizes — but keep the snapshot to this run rather
      // than arming pendingFreed with it. Until the apply has invalidated a
      // cleanup's cached size, the only reading the poller can see is the one
      // this snapshot was taken from, so a poll landing mid-run would resolve
      // "0 MB freed" for a cleanup that had not run yet and consume the pending
      // entry, leaving the real figure with nothing to report against.
      const before: Record<string, number> = {};
      for (const id of ids) {
        const setting = settings.get(id as SettingId);
        if (!setting || !SIZE_MODULES.has(setting.module)) continue;
        const mb = parseSizeToMB(setting.currentValue);
        if (mb !== null) before[id] = mb;
      }
      return { before };
    },
    onSuccess: (data, _ids, context) => {
      const before = context?.before ?? {};
      const runResults: CleanupResult[] = [];
      const failedOps: string[] = [];
      let armed = false;
      for (const [id, result] of Object.entries(data.results)) {
        const setting = settings.get(id as SettingId);
        const name = setting?.displayName ?? id;
        const sizeBearing = SIZE_MODULES.has(setting?.module ?? "");
        if (result.success) {
          // The apply invalidated this cleanup's cached size before answering,
          // so from here every reading is a post-run one and arming is safe.
          const sized = sizeBearing && before[id] !== undefined;
          if (sized) {
            pendingFreed[id] = { beforeMB: before[id], armedAt: Date.now() };
            armed = true;
          }
          runResults.push({ id, name, success: true, sized, freedMB: null });
        } else {
          delete pendingFreed[id];
          failedOps.push(`${id}: ${result.error}`);
          runResults.push({
            id,
            name,
            success: false,
            sized: false,
            freedMB: null,
            error: result.error ?? undefined,
          });
        }
      }
      if (runResults.length > 0) recordCleanupResults(runResults);
      if (failedOps.length > 0) log.error("Cleanup errors:", failedOps);

      if (data.success_count > 0) {
        addNotification(
          `Cleanup complete: ${data.success_count} operations succeeded`,
          "success",
        );
      }
      if (data.error_count > 0) {
        addNotification(
          `${data.error_count} cleanup operations failed`,
          "error",
        );
      }

      // Re-read the sizes now rather than waiting for the next poll tick, and
      // resolve against what comes back: a fast cleanup is often re-measured
      // before this handler runs, and the poll's effect only fires when the
      // sizes *change* — which, for a size that has already settled, they never
      // will again. `staleTime: 0` because the cached copy is the pre-run one
      // and the whole question is what the machine holds now.
      void queryClient
        .query({
          queryKey: ["cleanup-sizes"],
          queryFn: settingsApi.getCleanupSizes,
          staleTime: 0,
        })
        .then((sizes) => {
          if (armed) resolvePendingFreed(sizes);
        })
        .catch(() => {
          /* the poll picks the sizes up on its next tick */
        });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
    onError: (error) => {
      const msg = error instanceof Error ? error.message : "Unknown error";
      log.error("Request failed:", error);
      addNotification(`Cleanup failed: ${msg}`, "error");
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
  });

  const execute = (ids: string[], fromSelection: boolean) => {
    if (ids.length === 0) return;
    runMutation.mutate(ids);
    if (fromSelection) {
      // Deselect what we just ran (leave other-module selections intact).
      for (const id of ids) if (selection[id]) toggleMaintenanceSelection(id);
    }
  };

  const run = (ids?: string[]) => {
    const fromSelection = ids === undefined;
    const resolved = ids ?? selectedIds;
    if (resolved.length === 0) return;
    const hasDocker = resolved.some((id) => {
      const s = settings.get(id as SettingId);
      return s && isDockerCleanup(s);
    });
    if (hasDocker) {
      setConfirmIds(resolved);
      return;
    }
    execute(resolved, fromSelection);
  };

  return {
    selectedIds,
    selectedCount: selectedIds.length,
    hasSelection: selectedIds.length > 0,
    isRunning: runMutation.isPending,
    run,
    confirmIds,
    confirmRun: () => {
      if (confirmIds) execute(confirmIds, false);
      setConfirmIds(null);
    },
    cancelConfirm: () => setConfirmIds(null),
  };
}
