import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { settingsApi } from "../lib/api";
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
 */
const pendingFreed: Record<string, number> = {};
let detectTriggered = false;

/** Docker prune actions restart Docker + WSL, so they need a confirm gate. */
export function isDockerCleanup(s: Setting): boolean {
  return s.name === "docker_prune" || s.name === "docker_prune_all";
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
  const recordCleanupResults = useStore((s) => s.recordCleanupResults);

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
    const resolved: CleanupResult[] = [];
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

      const beforeMB = pendingFreed[id];
      if (beforeMB !== undefined) {
        delete pendingFreed[id];
        const setting = useStore.getState().settings.get(id as SettingId);
        resolved.push({
          id,
          name: setting?.displayName ?? id,
          success: true,
          sized: true,
          freedMB: Math.max(0, beforeMB - mb),
        });
      }
    }
    if (resolved.length > 0) recordCleanupResults(resolved);
  }, [cleanupSizes, setSettingDetectionResult, recordCleanupResults]);
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
    mutationFn: async (ids: string[]) => {
      const payload: Record<string, boolean> = {};
      for (const id of ids) payload[id] = true;
      return settingsApi.bulkApply(payload);
    },
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
      // Snapshot pre-cleanup sizes so freed space can be reported afterwards.
      for (const id of ids) {
        const setting = settings.get(id as SettingId);
        if (!setting || !SIZE_MODULES.has(setting.module)) continue;
        const mb = parseSizeToMB(setting.currentValue);
        if (mb !== null) pendingFreed[id] = mb;
      }
    },
    onSuccess: (data) => {
      const runResults: CleanupResult[] = [];
      const failedOps: string[] = [];
      for (const [id, result] of Object.entries(data.results)) {
        const setting = settings.get(id as SettingId);
        const name = setting?.displayName ?? id;
        const sizeBearing = SIZE_MODULES.has(setting?.module ?? "");
        if (result.success) {
          const sized = sizeBearing && pendingFreed[id] !== undefined;
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

      queryClient.invalidateQueries({ queryKey: ["cleanup-sizes"] });
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
