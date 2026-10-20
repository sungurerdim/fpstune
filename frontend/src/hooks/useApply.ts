import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useT } from "../i18n";
import { localizedName } from "../i18n/settings";
import { errorMessage, settingsApi, type ApplyResponse } from "../lib/api";
import { applyActionEvent, beginActionRun } from "../lib/actionRun";
import { bulkTargets, verifiedState } from "../lib/bulkStream";
import { detectionManager } from "../lib/detection-manager";
import { hardwareManager } from "../lib/hardware-manager";
import { useStore, type BulkAction } from "../store";
import { isDisplaySetting, type Setting } from "../types/setting";

/** A failed response for a request that never got one, so callers never see a rejection. */
function failedResponse(setting: Setting, error: string): ApplyResponse {
  return {
    setting_id: setting.id,
    success: false,
    error,
    state: null,
    requires_reboot: false,
    verified: null,
  };
}

/**
 * The one way the UI changes the machine: a single row, or many rows over the
 * one streamed bulk path.
 *
 * - `apply(setting, value)` / `reset(setting)`: one `POST /settings/{id}/apply`.
 *   Reset is an apply of the row's own default; there is no reset endpoint.
 *   The store is fed the `SettingState` the response carries — the backend's
 *   re-detect, `is_optimized` included. Nothing here compares a value to the
 *   recommendation.
 * - `run(action, ids)`: one `POST /settings/bulk/stream-apply` with
 *   `{id: value}` (`bulkTargets`), each row's outcome as it streams. A `verified`
 *   event carries the row's whole `SettingState` (the backend's verdict,
 *   `is_optimized` included), which goes into the store as it arrives, so a row
 *   is live before `done`. An action in the run (a cleanup, a repair) also gets
 *   its live step, its freed bytes and its post-run reading (`lib/actionRun.ts`).
 *   At the end, one batched re-detect of every id still runs:
 *   the rows with no state (failed, skipped, never reached) need it, and a
 *   verified row's state predates the writes that ran beside it. The run lives in the store, so
 *   switching tabs neither loses its Stop nor lets a second run start over it.
 *
 * Every outcome gets a visible confirmation, and every run invalidates
 * ["activity"] so successes and failures surface in the drawer.
 */
export function useApply() {
  const { t } = useT();
  const queryClient = useQueryClient();
  const addNotification = useStore((s) => s.addNotification);
  const bulkRun = useStore((s) => s.bulkRun);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  const write = useCallback(
    async (
      setting: Setting,
      value: unknown,
      kind: "apply" | "reset",
    ): Promise<ApplyResponse> => {
      setPendingIds((prev) => new Set(prev).add(setting.id));
      useStore.getState().beginOperation();
      try {
        const response = await settingsApi
          .applySetting(setting.id, value)
          .catch((error: unknown) => failedResponse(setting, errorMessage(error)));
        const name = localizedName(setting);
        if (response.success) {
          if (response.warnings && response.warnings.length > 0) {
            addNotification(
              t("apply.appliedWarnings", {
                name,
                reason: response.warnings[0],
              }),
              "warning",
            );
          } else {
            addNotification(
              t(kind === "apply" ? "apply.applied" : "apply.reset", { name }),
              "success",
            );
          }
          const state = response.state;
          if (state !== null && state.current !== null && state.current !== undefined) {
            useStore.getState().applySettingStates({ [setting.id]: state });
          } else {
            await detectionManager.redetectSettings([setting.id]);
          }
          if (isDisplaySetting(setting.id)) hardwareManager.refreshMonitors();
        } else {
          addNotification(
            t(kind === "apply" ? "apply.applyFailed" : "apply.resetFailed", {
              name,
              reason: response.error ?? t("apply.unknownError"),
            }),
            "error",
          );
          await detectionManager.redetectSettings([setting.id]);
        }
        return response;
      } finally {
        useStore.getState().endOperation();
        setPendingIds((prev) => {
          const next = new Set(prev);
          next.delete(setting.id);
          return next;
        });
        queryClient.invalidateQueries({ queryKey: ["activity"] });
      }
    },
    [addNotification, queryClient, t],
  );

  const apply = useCallback(
    (setting: Setting, value: unknown) => write(setting, value, "apply"),
    [write],
  );

  /** Write the row's own default (Windows stock, the driver's, or the game's, by domain). */
  const reset = useCallback(
    (setting: Setting) => write(setting, setting.defaultValue, "reset"),
    [write],
  );

  const run = useCallback(
    (action: BulkAction, ids: string[]) => {
      const store = useStore.getState();
      if (store.bulkRun || ids.length === 0) return;
      store.clearOperationStatus();
      ids.forEach((id) => store.setOperationStatus(id, "queued"));
      beginActionRun(ids);
      // The machine is being changed: the hardware re-read on window focus
      // stays off the same PowerShell for the length of the run.
      store.beginOperation();
      const warned = new Set<string>();

      const finish = () => {
        const state = useStore.getState();
        state.setBulkRun(null);
        state.endOperation();
        queryClient.invalidateQueries({ queryKey: ["activity"] });
        const status = state.operationStatus;
        const failed = ids.filter((id) => status[id] === "failed").length;
        const done = ids.filter(
          (id) => status[id] === "verified" || status[id] === "skipped",
        ).length;
        state.addNotification(
          t("toolbar.doneSummary", { done, failed }),
          failed > 0 || warned.size > 0 ? "warning" : "success",
        );
        if (warned.size > 0) {
          state.addNotification(t("toolbar.doneWarnings", { count: warned.size }), "warning");
        }
        // Every id is read again, failures included: a failed write can still
        // have changed part of what it touched, and a verified row's state
        // predates the writes that ran beside it, so this is the one reading
        // taken after the whole run settled.
        void detectionManager.redetectSettings(ids);
        if (ids.some(isDisplaySetting)) hardwareManager.refreshMonitors();
      };

      const cancel = settingsApi.bulkStreamApply(
        bulkTargets(ids, action),
        (event) => {
          const id = event.id as string | undefined;
          if (!id) return;
          applyActionEvent(event);
          const state = useStore.getState();
          if (event.event === "started" || event.event === "applied") {
            state.setOperationStatus(id, "running");
            if (
              event.event === "applied" &&
              Array.isArray(event.warnings) &&
              event.warnings.length > 0
            ) {
              warned.add(id);
            }
          } else if (event.event === "verified") {
            state.setOperationStatus(id, "verified");
            const settingState = verifiedState(event);
            if (settingState !== null) {
              state.applySettingStates({ [id]: settingState });
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

  return {
    apply,
    reset,
    run,
    stop,
    pendingIds,
    isPending: (id: string) => pendingIds.has(id),
    isRunning: bulkRun !== null,
  };
}
