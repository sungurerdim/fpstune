import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { errorMessage, settingsApi, BulkApplyResponse } from "../lib/api";
import { useT } from "../i18n";
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
  const { t } = useT();
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
    onSuccess: async (response, settings) => {
      // Every id in the request is re-read, failures included: a failed write
      // can still have changed part of what it touched.
      const touched = Object.keys(settings);
      if (touched.length > 0) {
        await detectionManager.redetectSettings(touched);
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
      if (response.success_count > 0 || realErrorCount > 0) {
        addNotification(
          t("bulk.summary", { applied: response.success_count, failed: realErrorCount }),
          realErrorCount === 0 ? "success" : response.success_count > 0 ? "warning" : "error",
        );
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
    onError: (error: Error, settings) => {
      log.error("Request failed:", error);
      addNotification(t("bulk.requestFailed", { reason: errorMessage(error) }), "error");
      void detectionManager.redetectSettings(Object.keys(settings));
      queryClient.invalidateQueries({ queryKey: ["activity"] });
      options.onError?.(error);
    },
  });

  return {
    // Never rejects: a failed request has already been reported above, and a
    // caller that fires and forgets must not turn it into an unhandled one.
    apply: async (settings) =>
      mutation.mutateAsync(settings).catch(() => ({
        results: {},
        success_count: 0,
        error_count: Object.keys(settings).length,
        requires_reboot: false,
      })),
    isApplying: mutation.isPending,
    lastResult,
  };
}
