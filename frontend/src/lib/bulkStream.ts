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

import type { SettingState } from "./api";
import { isTweakSuboptimal } from "./tweakStatus";
import type { BulkAction } from "../store";
import { canResetSetting, type Setting, type SettingId } from "../types/setting";

/**
 * The `SettingState` a streamed `verified` event carries, or null when it has none.
 *
 * The backend builds it with the same builder `/detect` and `/apply` use, so the
 * row can take it as it came (`is_optimized` included) the moment it lands.
 * Null is a real answer: no re-detect happened for that row, and the caller then
 * leaves it for the end-of-run re-detect rather than guessing a verdict.
 */
export function verifiedState(event: Record<string, unknown>): SettingState | null {
  const state = event.state;
  if (typeof state !== "object" || state === null) return null;
  const candidate = state as Partial<SettingState>;
  return typeof candidate.setting_id === "string" && typeof candidate.is_optimized === "boolean"
    ? (candidate as SettingState)
    : null;
}

/**
 * The value each id is sent with, from the store's own settings map.
 *
 * The map is passed in rather than read here: `lib` is the domain layer and the
 * store sits above it (dependency-cruiser's `lib-must-not-import-store`), so
 * the caller — `useApply`, which already has the store — hands over what it
 * knows.
 *
 * - apply: an action is run with `true`; anything else is written its
 *   recommendation.
 * - reset: every row's own default (Windows stock, the driver's default or the
 *   game's default, by domain). A row with no derivable default has `null`
 *   there, which the backend refuses rather than writes (C6).
 *
 * An id the map does not know is sent as `null`, so the stream reports it as
 * failed rather than the run silently asking for less than it was given.
 */
export function bulkTargets(
  settings: ReadonlyMap<SettingId, Setting>,
  ids: string[],
  action: BulkAction,
): Record<string, unknown> {
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

/** The settings each bulk action would touch in one scope. */
export interface ScopeTargets {
  /** Not optimized (the backend's `is_optimized`), and writable. */
  apply: Setting[];
  /** Writable, has a default of its own, and is not already at it. */
  reset: Setting[];
}

/**
 * Which settings in a scope each action would touch.
 *
 * Pure so the rule has one copy: a row, a device, a category heading, a page
 * header and a selection all ask the same question of a different set.
 * Advisories (`isReadonly`) are never targeted — fpstune can read them and
 * cannot write them, so counting one into a button would promise a write.
 */
export function scopeTargets(settings: Iterable<Setting>): ScopeTargets {
  const apply: Setting[] = [];
  const reset: Setting[] = [];
  for (const s of settings) {
    if (!s.isApplicable || s.isAction || s.isReadonly || s.currentValue === null) continue;
    if (isTweakSuboptimal(s)) apply.push(s);
    if (canResetSetting(s)) reset.push(s);
  }
  return { apply, reset };
}

/** The three bulk levels: each includes the ones before it. */
export type ScopeLevel = "essential" | "recommended" | "complete";

const LEVEL_SCOPES: Record<ScopeLevel, readonly Setting["scope"][]> = {
  essential: ["essential"],
  recommended: ["essential", "recommended"],
  complete: ["essential", "recommended", "complete"],
};

/**
 * What "apply <level>" would write in a scope: the not-optimized, writable
 * settings whose own `scope` is at or below the level. "Recommended" is
 * essential + recommended; "complete" adds the settings whose cost the player
 * reads in the setting's own copy.
 */
export function levelTargets(
  settings: Iterable<Setting>,
  level: ScopeLevel,
): Setting[] {
  const allowed = LEVEL_SCOPES[level];
  return scopeTargets(settings).apply.filter((s) => allowed.includes(s.scope));
}
