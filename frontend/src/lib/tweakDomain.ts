import type { MessageKey } from "../i18n/en";
import type {
  CategoryMetadata,
  DefaultSource,
  HardwareComponent,
  Setting,
  TweakDomain,
} from "../types/setting";

/**
 * Which page owns a tweak.
 *
 * The backend decides (`SettingExecutor.domain`): a tweak's category is the
 * physical component it acts on, never how it is set — PCIe link power saving is
 * a powercfg key and still a PCIe tweak. Every surface asks these predicates and
 * none re-derives the split from an id, so the three partition the registry and
 * nothing lands twice.
 */

/** True when a tweak is a line in a game's own config file. */
export function isGameTweak(setting: Setting): boolean {
  return setting.domain === "game";
}

/** True when a tweak acts on a physical component. */
export function isHardwareTweak(setting: Setting): boolean {
  return setting.domain === "hardware";
}

/** True for a software tweak: everything neither hardware nor a game's own file. */
export function isSoftwareTweak(setting: Setting): boolean {
  return setting.domain === "software";
}

/** True when a tweak acts on the named physical component. */
export function isComponentTweak(setting: Setting, component: HardwareComponent): boolean {
  return setting.component === component;
}

/**
 * The name of the default a domain's "Reset to default" writes back: Windows'
 * own value for a software tweak, the driver's for a component, the game's for
 * a line in its config file. One way back everywhere; only the word differs.
 */
const DEFAULT_KIND_KEY = {
  software: "reset.kind.software",
  hardware: "reset.kind.hardware",
  game: "reset.kind.game",
} as const satisfies Record<TweakDomain, MessageKey>;

/** The source the backend named -> the word the reset control shows. */
const DEFAULT_KIND_BY_SOURCE = {
  windows_stock: "reset.kind.software",
  driver: "reset.kind.hardware",
  scheme: "reset.kind.software",
  game: "reset.kind.game",
  application: "reset.kind.application",
  firmware: "reset.kind.firmware",
  none: "reset.kind.software",
} as const satisfies Record<DefaultSource, MessageKey>;

/** The default-kind word for one setting's real source, not its page. */
export function defaultKindKey(setting: Setting): MessageKey {
  const source = setting.defaultSource;
  return source ? DEFAULT_KIND_BY_SOURCE[source] : DEFAULT_KIND_KEY[setting.domain];
}

/** The one domain every setting in a scope shares, or "mixed" when they differ. */
export function scopeDomain(settings: readonly Setting[]): TweakDomain | "mixed" {
  const first = settings[0]?.domain;
  if (first === undefined) return "mixed";
  return settings.every((s) => s.domain === first) ? first : "mixed";
}

/** The three pages' worth of tweaks, each row in exactly one. */
export interface DomainPartition {
  software: Setting[];
  hardware: Setting[];
  game: Setting[];
}

/** Split settings by the backend's domain; the three lists never overlap. */
export function partitionByDomain(settings: Iterable<Setting>): DomainPartition {
  const out: DomainPartition = { software: [], hardware: [], game: [] };
  for (const s of settings) {
    if (isGameTweak(s)) out.game.push(s);
    else if (isHardwareTweak(s)) out.hardware.push(s);
    else out.software.push(s);
  }
  return out;
}

/** One heading's worth of settings: a game, a software category. */
export interface SettingGroup {
  id: string;
  /** The heading, in the words the backend sent. */
  label: string;
  order: number;
  settings: Setting[];
}

function collect(
  settings: Iterable<Setting>,
  keyOf: (s: Setting) => { id: string; label: string; order: number },
): SettingGroup[] {
  const groups = new Map<string, SettingGroup>();
  for (const s of settings) {
    const key = keyOf(s);
    let group = groups.get(key.id);
    if (!group) {
      group = { ...key, settings: [] };
      groups.set(key.id, group);
    }
    group.settings.push(s);
  }
  return [...groups.values()].sort(
    (a, b) => a.order - b.order || a.label.localeCompare(b.label),
  );
}

/**
 * A game's settings under that game, headed by the label the backend sent
 * (C9: no game's name is spelled here). A setting whose backend named no group
 * is listed under its own module rather than dropped: a setting the user cannot
 * find is worse than an ugly heading.
 */
export function gameGroups(settings: Iterable<Setting>): SettingGroup[] {
  return collect(settings, (s) => {
    const id = s.groupId ?? s.module;
    return { id, label: s.groupLabel ?? id, order: s.groupOrder ?? Number.MAX_SAFE_INTEGER };
  });
}

/**
 * Software settings under the category the backend files them in, in the
 * backend's category order; an unknown category sorts last under its own id.
 */
export function categoryGroups(
  settings: Iterable<Setting>,
  categories: ReadonlyMap<string, CategoryMetadata>,
): SettingGroup[] {
  return collect(settings, (s) => {
    const meta = categories.get(s.category);
    return {
      id: s.category,
      label: meta?.displayName ?? s.category,
      order: meta?.order ?? Number.MAX_SAFE_INTEGER,
    };
  });
}
