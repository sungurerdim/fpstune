import { useMemo } from "react";
import { canUndoSetting, valuesEqual, type Setting } from "../types/setting";
import { isTweakSuboptimal } from "../lib/tweakStatus";
import { useBulkStream } from "./useBulkStream";
import type { BulkAction } from "../store";

/** The ids each action would touch in one scope. */
export interface ScopeTargets {
  /** Not at the recommended value, and writable. */
  apply: Setting[];
  /** A recorded original that differs from what the machine holds now. */
  undo: Setting[];
  /** Writable and not already at the Windows default. */
  reset: Setting[];
}

/**
 * Which settings in a scope each action would touch.
 *
 * Pure so the rule has one copy: a row, a device card, a category heading, a
 * page header and a selection all ask the same question of a different set.
 * Advisories (`isReadonly`) are never targeted — fpstune can read them and
 * cannot write them, so counting one into a button would promise a write.
 */
export function scopeTargets(settings: Iterable<Setting>): ScopeTargets {
  const apply: Setting[] = [];
  const undo: Setting[] = [];
  const reset: Setting[] = [];
  for (const s of settings) {
    if (!s.isApplicable || s.isAction || s.isReadonly || s.currentValue === null) continue;
    if (isTweakSuboptimal(s)) apply.push(s);
    if (canUndoSetting(s)) undo.push(s);
    if (!valuesEqual(s.currentValue, s.defaultValue)) reset.push(s);
  }
  return { apply, undo, reset };
}

/**
 * Apply, undo and Windows-default over one scope, through the one streamed run.
 *
 * Every scope — row, group, page, selection — starts the same `useBulkStream`
 * run, so each row shows its own outcome and Stop works wherever it was started.
 */
export function useScopedActions(settings: readonly Setting[]) {
  const { run, stop, isRunning } = useBulkStream();
  const targets = useMemo(() => scopeTargets(settings), [settings]);
  const start = (action: BulkAction) =>
    run(
      action,
      targets[action].map((s) => s.id),
    );
  return { targets, start, stop, isRunning };
}
