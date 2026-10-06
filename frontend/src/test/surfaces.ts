/**
 * Every component that renders a setting's text, found in the source tree.
 *
 * The narrow-width test used to hold a hand-picked list of surfaces, and a
 * surface nobody listed (the readonly branch of `TweakSetting`, the Home
 * advisory cards) shipped overflowing its frame. A component belongs here when
 * its source imports from `types/setting`: that import is what it takes to
 * render a setting's fields. A new component that renders settings is therefore
 * found without anyone editing a list, and the test either renders it or
 * demands an explicit, reasoned exclusion.
 */

import type { ComponentType } from "react";

const SOURCES = import.meta.glob(["../components/**/*.tsx", "!../components/**/__tests__/**"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const MODULES = import.meta.glob(["../components/**/*.tsx", "!../components/**/__tests__/**"], {
  eager: true,
}) as Record<string, Record<string, unknown>>;

const IMPORTS_SETTING = /from\s+"\.\.\/(?:\.\.\/)?types\/setting"/;

export interface DiscoveredSurface {
  /** `components/ActionRow.tsx#ActionRow`: unique and stable. */
  id: string;
  /** The exported component's name. */
  name: string;
  Component: ComponentType<Record<string, unknown>>;
}

export function discoverSurfaces(): DiscoveredSurface[] {
  const found: DiscoveredSurface[] = [];
  for (const [path, source] of Object.entries(SOURCES)) {
    if (!IMPORTS_SETTING.test(source)) continue;
    const exports = MODULES[path] ?? {};
    for (const [name, value] of Object.entries(exports)) {
      if (!/^[A-Z]/.test(name) || typeof value !== "function") continue;
      found.push({
        id: `${path.replace("../", "")}#${name}`,
        name,
        Component: value as ComponentType<Record<string, unknown>>,
      });
    }
  }
  return found.sort((a, b) => a.id.localeCompare(b.id));
}
