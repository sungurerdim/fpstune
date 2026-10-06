import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { errorMessage, settingsApi, type ApplyResponse } from "../lib/api";
import { useT } from "../i18n";
import { localizedName } from "../i18n/settings";
import { useStore } from "../store";
import { hardwareManager } from "../lib/hardware-manager";
import { detectionManager } from "../lib/detection-manager";
import { isDisplaySetting, valuesEqual, type Setting } from "../types/setting";

/**
 * Shared single-setting apply. Extracted from ModuleCard so the list rows and
 * the cards apply identically: POST apply, then update the store from the
 * backend-detected new_value (fallback: re-detect). Always invalidates
 * ["activity"] so successes AND failures surface in the drawer.
 */
/** A failed response for a request that never got one, so callers never see a rejection. */
function failedResponse(setting: Setting, error: string): ApplyResponse {
  return {
    setting_id: setting.id,
    success: false,
    error,
    new_value: null,
    requires_reboot: false,
    verified: null,
  };
}

export function useApplySingle() {
  const { t } = useT();
  const queryClient = useQueryClient();
  const setSettingDetectionResult = useStore(
    (s) => s.setSettingDetectionResult,
  );
  // Every outcome gets a visible confirmation (E8): applying a tweak from
  // Home used to change the machine with no on-screen acknowledgement at all.
  const addNotification = useStore((s) => s.addNotification);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  const applySingle = useCallback(
    async (setting: Setting, value: unknown): Promise<ApplyResponse> => {
      setPendingIds((prev) => new Set(prev).add(setting.id));
      useStore.getState().beginOperation();
      try {
        const response = await settingsApi
          .applySetting(setting.id, value)
          .catch((error: unknown) => failedResponse(setting, errorMessage(error)));
        const name = localizedName(setting);
        if (response.success) {
          addNotification(t("apply.applied", { name }), "success");
          if (response.new_value !== null && response.new_value !== undefined) {
            const isOptimized = valuesEqual(
              response.new_value,
              setting.recommendedValue,
            );
            setSettingDetectionResult(
              setting.id,
              response.new_value,
              isOptimized,
              true,
            );
          } else {
            await detectionManager.redetectSettings([setting.id]);
          }
          if (isDisplaySetting(setting.id)) hardwareManager.refreshMonitors();
        } else {
          addNotification(
            t("apply.applyFailed", { name, reason: response.error ?? t("apply.unknownError") }),
            "error",
          );
          await detectionManager.redetectSettings([setting.id]);
        }
        return response;
      } finally {
        useStore.getState().endOperation();
        setPendingIds((prev) => {
          const n = new Set(prev);
          n.delete(setting.id);
          return n;
        });
        queryClient.invalidateQueries({ queryKey: ["activity"] });
      }
    },
    [addNotification, queryClient, setSettingDetectionResult, t],
  );

  /**
   * Write the setting's own default (Windows stock, the driver's default or the
   * game's default, by domain) through the dedicated endpoint.
   *
   * Not `applySingle(setting, setting.defaultValue)`: the write is the same,
   * but through /apply the backend never knew it was a reset — the activity
   * log recorded an apply, and the /reset route (which detects, writes the
   * default, and verifies against it) sat uncalled.
   */
  const resetSingle = useCallback(
    async (setting: Setting): Promise<ApplyResponse> => {
      setPendingIds((prev) => new Set(prev).add(setting.id));
      useStore.getState().beginOperation();
      try {
        const response = await settingsApi
          .resetSetting(setting.id)
          .catch((error: unknown) => failedResponse(setting, errorMessage(error)));
        const name = localizedName(setting);
        if (response.success) {
          addNotification(t("apply.reset", { name }), "success");
          if (response.new_value !== null && response.new_value !== undefined) {
            const isOptimized = valuesEqual(
              response.new_value,
              setting.recommendedValue,
            );
            setSettingDetectionResult(
              setting.id,
              response.new_value,
              isOptimized,
              true,
            );
          } else {
            await detectionManager.redetectSettings([setting.id]);
          }
          if (isDisplaySetting(setting.id)) hardwareManager.refreshMonitors();
        } else {
          addNotification(
            t("apply.resetFailed", { name, reason: response.error ?? t("apply.unknownError") }),
            "error",
          );
          await detectionManager.redetectSettings([setting.id]);
        }
        return response;
      } finally {
        useStore.getState().endOperation();
        setPendingIds((prev) => {
          const n = new Set(prev);
          n.delete(setting.id);
          return n;
        });
        queryClient.invalidateQueries({ queryKey: ["activity"] });
      }
    },
    [addNotification, queryClient, setSettingDetectionResult, t],
  );

  return {
    applySingle,
    resetSingle,
    pendingIds,
    isPending: (id: string) => pendingIds.has(id),
  };
}
