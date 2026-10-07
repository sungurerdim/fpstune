/**
 * The client side of the one bulk path (`POST /settings/bulk/stream-apply`).
 *
 * The server derives no value: the request is a map of setting id to the value
 * to write, so "apply recommended" and "reset to default" are the same call
 * with different maps. `bulkTargets` is where those maps are made, and the one
 * place that knows an action is run with `true` — an action's own
 * `recommendedValue` answers a different question (whether fpstune suggests
 * running it unprompted), and for 24 of the 38 shipped actions the answer is
 * `false`, which the backend reads as "do not run" and reports as success.
 */

import { settingsApi, type ApplyResponse } from "./api";
import { useStore, type BulkAction } from "../store";
import type { SettingId } from "../types/setting";

/** The outcome of a bulk run, assembled from the events it streamed. */
export interface BulkApplyResponse {
  results: Record<string, ApplyResponse>;
  /** Rows that were written and verified. A skipped row is neither a success nor an error. */
  success_count: number;
  error_count: number;
  requires_reboot: boolean;
}

/**
 * The value each id is sent with.
 *
 * - apply: an action is run with `true`; anything else is written its
 *   recommendation.
 * - reset: every row's own default (Windows stock, the driver's default or the
 *   game's default, by domain). A row with no derivable default has `null`
 *   there, which the backend refuses rather than writes (C6).
 *
 * An id the store does not know is sent as `null`, so the stream reports it as
 * failed rather than the run silently asking for less than it was given.
 */
export function bulkTargets(
  ids: string[],
  action: BulkAction,
): Record<string, unknown> {
  const settings = useStore.getState().settings;
  const targets: Record<string, unknown> = {};
  for (const id of ids) {
    const setting = settings.get(id as SettingId);
    if (setting === undefined) {
      targets[id] = null;
    } else if (action === "reset") {
      targets[id] = setting.defaultValue ?? null;
    } else {
      targets[id] = setting.isAction ? true : (setting.recommendedValue ?? null);
    }
  }
  return targets;
}

/**
 * Apply the map through the stream and answer once it is done.
 *
 * For the caller that wants the outcome rather than the live rows (Home's
 * "apply what is left"). Rejects when the stream itself dies: a promise waiting
 * for a `done` that is never coming would leave its button busy for the rest of
 * the session.
 */
export function applyStreamed(
  settings: Record<string, unknown>,
): Promise<BulkApplyResponse> {
  return new Promise<BulkApplyResponse>((resolve, reject) => {
    const results: Record<string, ApplyResponse> = {};
    let requiresReboot = false;

    settingsApi.bulkStreamApply(
      settings,
      (event) => {
        const id = typeof event.id === "string" ? event.id : "";
        if (!id) return;
        switch (event.event) {
          case "applied":
            requiresReboot = requiresReboot || event.requires_reboot === true;
            results[id] = {
              setting_id: id,
              success: true,
              error: null,
              state: null,
              requires_reboot: event.requires_reboot === true,
              skipped: false,
              verified: null,
            };
            return;
          case "verified":
            if (results[id] !== undefined) {
              results[id].verified =
                typeof event.matches === "boolean" ? event.matches : null;
            }
            return;
          case "skipped":
            results[id] = {
              setting_id: id,
              success: true,
              error: null,
              state: null,
              requires_reboot: false,
              skipped: true,
              verified: null,
            };
            return;
          case "failed":
            results[id] = {
              setting_id: id,
              success: false,
              error:
                typeof event.error === "string" && event.error
                  ? event.error
                  : "Unknown error",
              state: null,
              requires_reboot: false,
              skipped: false,
              verified: null,
            };
            return;
          default:
            return;
        }
      },
      () => {
        const values = Object.values(results);
        resolve({
          results,
          success_count: values.filter((r) => r.success && !r.skipped).length,
          error_count: values.filter((r) => !r.success).length,
          requires_reboot: requiresReboot,
        });
      },
      (error) =>
        reject(error instanceof Error ? error : new Error(String(error))),
    );
  });
}
