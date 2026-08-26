import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { settingsApi, type ApplyResponse } from "../lib/api";
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
export function useApplySingle() {
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
      try {
        const response = await settingsApi.applySetting(setting.id, value);
        if (response.success) {
          addNotification(`Applied ${setting.displayName}`, "success");
          if (
            response.new_value !== null &&
            response.new_value !== undefined
          ) {
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
            `Could not apply ${setting.displayName}: ${response.error ?? "unknown error"}`,
            "error",
          );
        }
        return response;
      } finally {
        setPendingIds((prev) => {
          const n = new Set(prev);
          n.delete(setting.id);
          return n;
        });
        queryClient.invalidateQueries({ queryKey: ["activity"] });
      }
    },
    [addNotification, queryClient, setSettingDetectionResult],
  );

  /**
   * Put one setting back to what this machine held before fpstune touched it.
   *
   * Goes through the dedicated endpoint rather than applying `originalValue`
   * itself, because the backend does two things beyond the write that a plain
   * apply would skip: it creates a restore point, and it drops the recorded
   * original once the machine is actually back, so the next scan is free to
   * record a fresh one. A 409 means nothing was recorded — the UI should not
   * have offered the action, so the row is re-detected to resync.
   */
  const undoSingle = useCallback(
    async (setting: Setting): Promise<ApplyResponse | null> => {
      setPendingIds((prev) => new Set(prev).add(setting.id));
      try {
        const response = await settingsApi.undoSetting(setting.id);
        if (response.success) {
          addNotification(`Undid ${setting.displayName}`, "success");
        }
        // Always re-detect: the value changed and the original is now gone, and
        // both of those live in the detection result the row renders from.
        await detectionManager.redetectSettings([setting.id]);
        if (response.success && isDisplaySetting(setting.id)) {
          hardwareManager.refreshMonitors();
        }
        return response;
      } catch {
        addNotification(`Could not undo ${setting.displayName}`, "error");
        await detectionManager.redetectSettings([setting.id]);
        return null;
      } finally {
        setPendingIds((prev) => {
          const n = new Set(prev);
          n.delete(setting.id);
          return n;
        });
        queryClient.invalidateQueries({ queryKey: ["activity"] });
      }
    },
    [addNotification, queryClient],
  );

  /**
   * Write the curated Windows-stock value through the dedicated endpoint.
   *
   * Not `applySingle(setting, setting.defaultValue)`: the write is the same,
   * but through /apply the backend never knew it was a reset — the activity
   * log recorded an apply, and the /reset route (which detects, writes the
   * stock value, and verifies against it) sat uncalled.
   */
  const resetSingle = useCallback(
    async (setting: Setting): Promise<ApplyResponse> => {
      setPendingIds((prev) => new Set(prev).add(setting.id));
      try {
        const response = await settingsApi.resetSetting(setting.id);
        if (response.success) {
          addNotification(
            `Reset ${setting.displayName} to the Windows default`,
            "success",
          );
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
            `Could not reset ${setting.displayName}: ${response.error ?? "unknown error"}`,
            "error",
          );
        }
        return response;
      } finally {
        setPendingIds((prev) => {
          const n = new Set(prev);
          n.delete(setting.id);
          return n;
        });
        queryClient.invalidateQueries({ queryKey: ["activity"] });
      }
    },
    [addNotification, queryClient, setSettingDetectionResult],
  );

  return {
    applySingle,
    resetSingle,
    undoSingle,
    pendingIds,
    isPending: (id: string) => pendingIds.has(id),
  };
}
