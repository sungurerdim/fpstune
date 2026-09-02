import { getLocale } from "./index";
import { settingsTr } from "./settingsTr";
import type { Setting } from "../types/setting";

/**
 * Setting copy, translated at the edge (F3's recorded decision).
 *
 * The backend stays English per C4 — descriptions are code-adjacent prose
 * reviewed against the registry — and the Turkish forms live here, keyed by
 * setting id. Per-adapter settings carry a machine-specific interface index
 * in their id (network:17:eee), which must never appear in source (C9), so
 * they fall back to a name-keyed table matched on the id's stable last
 * segment. An id neither table knows falls back to the English copy —
 * honest, and visible, rather than a blank.
 */

const PER_ADAPTER = /^network:\d+:(.+)$/;

function entryFor(
  id: string,
): { name?: string; description?: string; effect?: string } | undefined {
  const direct = settingsTr[id];
  if (direct) return direct;
  const adapter = PER_ADAPTER.exec(id);
  if (adapter) return settingsTr["network:*:" + adapter[1]];
  return undefined;
}

/** The plain name the row leads with, in the active locale. */
export function localizedName(setting: Setting): string {
  const english = setting.shortName || setting.displayName;
  if (getLocale() !== "tr") return english;
  return entryFor(setting.id)?.name || english;
}

/**
 * The description the tooltip and rows show, in the active locale.
 *
 * An empty Turkish description is deliberate: machine-derived descriptions
 * (panel refresh ceilings, VRAM budgets) are composed per machine by the
 * backend, so a static translation would freeze one machine's numbers into
 * source (C9). Empty falls through to the English, machine-correct text.
 */
export function localizedDescription(setting: Setting): string {
  if (getLocale() !== "tr") return setting.description;
  return entryFor(setting.id)?.description || setting.description;
}

/**
 * The advisory's "what you can do" sentence, in the active locale.
 *
 * `effect` is the one line a finding fpstune cannot fix exists for — the cable
 * to change, the band to join. English falls through when the catalogue has no
 * Turkish form, the same way the description does.
 */
export function localizedEffect(setting: Setting): string {
  const english = setting.effect ?? "";
  if (getLocale() !== "tr") return english;
  return entryFor(setting.id)?.effect || english;
}
