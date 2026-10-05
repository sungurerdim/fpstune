import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useT } from "../i18n";
import { errorMessage, settingsApi } from "../lib/api";
import { detectionManager } from "../lib/detection-manager";
import { useStore, type BulkAction } from "../store";
import { valuesEqual, type SettingId } from "../types/setting";

/**
 * One streamed bulk apply, reset or undo at a time, shared by every surface that
 * starts one. The run lives in the store, so switching tabs neither loses its
 * Stop nor lets a second run start over it; every row shows how far it got and,
 * when it failed, why; and however the run ends, every row is read again.
 */
export function useBulkStream() {
  const { t } = useT();
  const queryClient = useQueryClient();
  const bulkRun = useStore((s) => s.bulkRun);

  const run = useCallback(
    (action: BulkAction, ids: string[]) => {
      const store = useStore.getState();
      if (store.bulkRun || ids.length === 0) return;
      store.clearOperationStatus();
      ids.forEach((id) => store.setOperationStatus(id, "queued"));
      // The machine is being changed: the hardware re-read on window focus
      // stays off the same PowerShell for the length of the run.
      store.beginOperation();

      const finish = () => {
        const state = useStore.getState();
        state.setBulkRun(null);
        state.endOperation();
        queryClient.invalidateQueries({ queryKey: ["activity"] });
        queryClient.invalidateQueries({ queryKey: ["history"] });
        const status = state.operationStatus;
        const failed = ids.filter((id) => status[id] === "failed").length;
        const done = ids.filter(
          (id) => status[id] === "verified" || status[id] === "skipped",
        ).length;
        state.addNotification(
          t("toolbar.doneSummary", { done, failed }),
          failed > 0 ? "warning" : "success",
        );
        void detectionManager.redetectSettings(ids);
      };

      const stream = {
        apply: settingsApi.bulkStreamApply,
        reset: settingsApi.bulkStreamReset,
        undo: settingsApi.bulkStreamUndo,
      }[action];
      const cancel = stream(
        ids,
        (event) => {
          const id = event.id as string | undefined;
          if (!id) return;
          const state = useStore.getState();
          if (event.event === "started" || event.event === "applied") {
            state.setOperationStatus(id, "running");
          } else if (event.event === "verified") {
            state.setOperationStatus(id, "verified");
            // The stream carries the read-back, so the row needs no extra call.
            const currentValue = event.current_value;
            const setting = state.settings.get(id as SettingId);
            if (setting !== undefined && currentValue !== undefined) {
              state.setSettingDetectionResult(
                id as SettingId,
                currentValue,
                valuesEqual(currentValue, setting.recommendedValue),
                true,
              );
            }
          } else if (event.event === "failed") {
            state.setOperationStatus(id, "failed", (event.error as string) || undefined);
          } else if (event.event === "skipped") {
            state.setOperationStatus(id, "skipped");
          }
        },
        finish,
        (error) => {
          // The stream died before `done`: every row it never reached failed,
          // and says why.
          const reason = errorMessage(error);
          const state = useStore.getState();
          ids.forEach((id) => {
            const status = state.operationStatus[id];
            if (status === "queued" || status === "running") {
              state.setOperationStatus(id, "failed", reason);
            }
          });
          state.addNotification(t("toolbar.streamFailed", { reason }), "error");
          finish();
        },
      );
      store.setBulkRun({ action, cancel });
    },
    [queryClient, t],
  );

  const stop = useCallback(() => {
    const state = useStore.getState();
    const current = state.bulkRun;
    if (!current) return;
    current.cancel();
    // Rows keep where they got to; those never reached are marked so, and
    // every row is read again because the machine is what changed.
    const ids = Object.keys(state.operationStatus);
    ids.forEach((id) => {
      if (state.operationStatus[id] === "queued") state.setOperationStatus(id, "skipped");
    });
    state.setBulkRun(null);
    state.endOperation();
    state.addNotification(t("toolbar.stopped"), "info");
    void detectionManager.redetectSettings(ids);
  }, [t]);

  return { run, stop, isRunning: bulkRun !== null };
}
