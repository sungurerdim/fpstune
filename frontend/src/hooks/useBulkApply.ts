import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { settingsApi, BulkApplyResponse } from "../lib/api";
import { useStore } from "../store";
import { hardwareManager } from "../lib/hardware-manager";
import { isDisplaySetting } from "../types/setting";
import { detectionManager } from "../lib/detection-manager";
import { createLogger } from "../lib/logger";

const log = createLogger("useBulkApply");

interface UseBulkApplyOptions {
  onSuccess?: (response: BulkApplyResponse) => void;
  onError?: (error: Error) => void;
}

interface UseBulkApplyResult {
  apply: (settings: Record<string, unknown>) => Promise<BulkApplyResponse>;
  isApplying: boolean;
  lastResult: { success: number; error: number } | null;
}

/**
 * Shared hook for bulk apply operations.
 * Replaces duplicate useMutation patterns across components.
 *
 * Usage:
 * const { apply, isApplying, lastResult } = useBulkApply({
 * })
 *
 * // Apply settings
 * await apply({ 'timer:hpet': 'disabled', 'power:usb': 'disabled' })
 */
export function useBulkApply(
  options: UseBulkApplyOptions = {},
): UseBulkApplyResult {
  const queryClient = useQueryClient();
  const addNotification = useStore((s) => s.addNotification);
  const [lastResult, setLastResult] = useState<{
    success: number;
    error: number;
  } | null>(null);

  const mutation = useMutation({
    onMutate: () => useStore.getState().beginOperation(),
    onSettled: () => useStore.getState().endOperation(),
    mutationFn: (settings: Record<string, unknown>) =>
      settingsApi.bulkApply(settings),
    onSuccess: async (response) => {
      // Collect all applied setting IDs for re-detection
      const appliedSettingIds = Object.entries(response.results)
        .filter(([, result]) => result.success)
        .map(([settingId]) => settingId);

      // Re-detect all applied settings to get actual current values from system
      // This ensures UI reflects the true state, not just what we think we set
      if (appliedSettingIds.length > 0) {
        await detectionManager.redetectSettings(appliedSettingIds);
      }

      // Count skipped (non-applicable) separately from real errors
      const skippedCount = Object.values(response.results).filter(
        (r) => r.skipped,
      ).length;
      const realErrorCount = response.error_count - skippedCount;

      // Log errors for failed settings (not skipped)
      if (realErrorCount > 0) {
        const failedSettings: string[] = [];
        for (const [settingId, result] of Object.entries(response.results)) {
          if (!result.success && !result.skipped && result.error) {
            failedSettings.push(`${settingId}: ${result.error}`);
          }
        }
        log.error("Apply errors:", failedSettings);
      }

      setLastResult({ success: response.success_count, error: realErrorCount });
      // The visible confirmation (E8): a bulk write must never finish silently.
      if (response.success_count > 0) {
        addNotification(
          `Applied ${response.success_count} setting${
            response.success_count === 1 ? "" : "s"
          }${realErrorCount > 0 ? ` — ${realErrorCount} failed` : ""}`,
          realErrorCount > 0 ? "warning" : "success",
        );
      } else if (realErrorCount > 0) {
        addNotification(`Apply failed for ${realErrorCount} settings`, "error");
      }
      // Surface successes AND failures in the Activity drawer promptly.
      queryClient.invalidateQueries({ queryKey: ["activity"] });

      // Refresh monitors if display-related settings were changed (fast, ~200ms)
      const hasDisplayChanges = Object.keys(response.results).some(
        isDisplaySetting,
      );
      if (hasDisplayChanges) {
        hardwareManager.refreshMonitors();
      }

      options.onSuccess?.(response);
    },
    onError: (error: Error) => {
      log.error("Request failed:", error);
      options.onError?.(error);
    },
  });

  return {
    apply: async (settings) => mutation.mutateAsync(settings),
    isApplying: mutation.isPending,
    lastResult,
  };
}
