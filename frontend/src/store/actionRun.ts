/**
 * What a run of actions (cleanups, repairs) writes into the store while it streams.
 *
 * A cleanup is a setting like any other as far as the one apply path goes, but
 * three things a tweak has no use for ride its events: the command's own output
 * and percentage (a DISM repair runs for half an hour, and without them it is one
 * spinner, indistinguishable from a wedged one), the bytes the backend measured
 * either side of the run, and the reading it took afterwards.
 *
 * C11 holds throughout. A percentage is one the command printed; a step that
 * prints none shows elapsed seconds. A freed figure is `freed_bytes` — the
 * backend's own before-and-after pair — or nothing: an event that carries none
 * is a cleanup that ran and could not say what it reclaimed, recorded as such
 * rather than as zero.
 */

import { useStore } from "./index";
import { parseActionReading } from "../lib/actionReading";
import { detectionManager } from "./detection-manager";
import type { Setting, SettingId } from "../types/setting";

const BYTES_PER_MB = 1048576;

const asText = (value: unknown): string => (typeof value === "string" ? value : "");
const asBytes = (value: unknown): number | null =>
  typeof value === "number" ? value : null;

/** Docker prune actions restart Docker + WSL, so they need a confirm gate. */
export function isDockerCleanup(s: Setting): boolean {
  return s.name === "docker_prune" || s.name === "docker_prune_all";
}

/** Open a run for the ids that are actions; tweaks in the same run have no steps. */
export function beginActionRun(ids: readonly string[]): void {
  const { settings, beginRun } = useStore.getState();
  const steps = ids.flatMap((id) => {
    const setting = settings.get(id as SettingId);
    return setting?.isAction ? [{ id, name: setting.displayName }] : [];
  });
  if (steps.length > 0) beginRun(steps);
}

/** Feed one stream event of the apply run into the action's live step and result. */
export function applyActionEvent(event: Record<string, unknown>): void {
  const id = asText(event.id);
  const store = useStore.getState();
  const step = store.runSteps.find((s) => s.id === id);
  if (!id || !step) return;

  switch (event.event) {
    case "started":
      store.updateRunStep(id, {
        status: "running",
        startedAt: Date.now(),
        name: asText(event.name) || undefined,
        durationEstimate: asText(event.duration_estimate),
        reportsProgress: event.reports_progress === true,
      });
      return;
    case "output": {
      const text = asText(event.text);
      // The command itself is the first line the backend sends, so the row can
      // show what is running before it has run.
      if (!step.command) store.updateRunStep(id, { command: text });
      else store.appendRunOutput(id, text, event.replaces === true);
      if (typeof event.percent === "number") {
        store.updateRunStep(id, { percent: event.percent });
      }
      return;
    }
    case "applied": {
      const freedBytes = asBytes(event.freed_bytes);
      const sizeAfterBytes = asBytes(event.size_after_bytes);
      store.recordCleanupResults([
        {
          id,
          name: step.name,
          success: true,
          sized: freedBytes !== null,
          freedMB: freedBytes !== null ? freedBytes / BYTES_PER_MB : null,
        },
      ]);
      store.updateRunStep(id, { status: "done", endedAt: Date.now(), percent: 100 });
      // One docker prune changes the other's reclaimable estimate, and the
      // backend invalidated both caches: read both again.
      const ran = store.settings.get(id as SettingId);
      if (ran && isDockerCleanup(ran)) {
        const dockerIds = [...store.settings.values()]
          .filter((s) => isDockerCleanup(s) && s.isApplicable)
          .map((s) => s.id);
        detectionManager.redetectSettings(dockerIds).catch(() => {});
      }
      // What the row can still reclaim, now, from the same reading, so a finished
      // cleanup stops advertising the size it had before it ran.
      if (sizeAfterBytes !== null) {
        store.setSettingDetectionResult(
          id as SettingId,
          `ready|${Math.round(sizeAfterBytes / BYTES_PER_MB)} MB`,
          false,
          true,
        );
        return;
      }
      // An action that reports a state rather than a byte count (the SSD retrim
      // answers `ok|0 days` the moment it finishes): the backend's own post-run
      // reading, stored verbatim. An event with none leaves the previous reading
      // for the next detection pass to correct.
      const currentValue = asText(event.current_value);
      const reading = parseActionReading(currentValue);
      if (reading !== null) {
        store.setSettingDetectionResult(
          id as SettingId,
          currentValue,
          reading.kind === "ok",
          true,
        );
      }
      return;
    }
    case "skipped":
      store.updateRunStep(id, { status: "skipped", endedAt: Date.now() });
      return;
    case "failed": {
      const error = asText(event.error) || "Unknown error";
      store.recordCleanupResults([
        { id, name: step.name, success: false, sized: false, freedMB: null, error },
      ]);
      store.updateRunStep(id, { status: "failed", endedAt: Date.now(), error });
      return;
    }
    default:
      // `verified` and `done` carry nothing the rows do not already have.
      return;
  }
}
