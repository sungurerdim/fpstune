import { useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "../lib/api";
import { detectionManager } from "../lib/detection-manager";
import { useStore } from "../store";
import type { SettingId } from "../types/setting";

/** Modules whose actions report a reclaimable size (freed-space tracking). */
const SIZE_MODULES = new Set(["cleanup", "game_cleanup"]);

/**
 * Module-level state so the one-time size detection fires exactly once per
 * session regardless of which tab mounted first.
 */
let detectTriggered = false;

/**
 * Mounted once via <CleanupRunnerProvider/>: kicks off the one-time size
 * detection for every size-bearing cleanup, polls ["cleanup-sizes"] until every
 * size has settled, and syncs the results into the store. Runs regardless of
 * the active tab.
 *
 * It measures the *opening* state and nothing else. Freed space is no longer
 * inferred here from a before/after pair the frontend held: the backend takes
 * both readings around the cleanup it runs and reports the difference on the
 * `applied` event, which is the only place both sides of it are known to belong
 * to the same run.
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
  // came to blank `recommended_value` on everything it touched. There is one mapping and every caller uses it.
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

  // Sync completed sizes into the store.
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
  }, [cleanupSizes, setSettingDetectionResult]);
}
