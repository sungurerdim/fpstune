/**
 * F4 GATE: every user-facing string has an English and a Turkish form.
 *
 * Three mechanical halves, honest about their reach (V4):
 * - Catalogue parity is the type-checker's (tr is Record<keyof en, string>);
 *   here the runtime re-checks it plus the thing types cannot see — that a
 *   {placeholder} used by one locale exists in the other, so interpolation
 *   cannot silently print "{count}" in Turkish.
 * - The untranslated-component baseline: every .tsx component that does not
 *   yet speak through the i18n layer is frozen below. The list may only
 *   shrink — a NEW component that ships raw English fails immediately, and a
 *   migrated one turns its entry stale. This is F2/F3's migration ledger.
 * - The backend register half (short_name coverage, C3 format) lives in
 *   tests/test_quality_gates.py::TestF4CopyRegister.
 */

import { describe, it, expect } from "vitest";
import { en } from "../i18n/en";
import { tr } from "../i18n/tr";

const COMPONENTS = import.meta.glob("../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// Frozen at the F1 landing: the components that still speak raw English.
// Shrink-only. FirstRunNotice, HomeTab and TabNavigation are absent because
// they migrated with the infrastructure.
const _UNTRANSLATED_BASELINE = new Set([
  "App.tsx", // string-free or prop-fed — nothing to migrate
  "components/CleanupRunnerProvider.tsx", // string-free or prop-fed — nothing to migrate
  // string-free (renders HardwarePanel only) — nothing to migrate:
  "components/HardwareTab.tsx",
  "components/TweakRows.tsx", // string-free or prop-fed — nothing to migrate
  "components/ui/Badge.tsx", // string-free or prop-fed — nothing to migrate
  "components/ui/Button.tsx", // string-free or prop-fed — nothing to migrate
  "components/ui/Card.tsx", // string-free or prop-fed — nothing to migrate
  "components/ui/Feedback.tsx", // string-free or prop-fed — nothing to migrate
  "components/ui/LoadingSpinner.tsx", // string-free or prop-fed — nothing to migrate
  "components/ui/PillSelector.tsx", // string-free or prop-fed — nothing to migrate
  "components/ui/StatusChip.tsx", // string-free or prop-fed — nothing to migrate
  "components/ui/ToggleSwitch.tsx", // string-free or prop-fed — nothing to migrate
  "components/ui/tooltip.tsx", // string-free or prop-fed — nothing to migrate
  "main.tsx", // string-free or prop-fed — nothing to migrate
]);

function speaksThroughI18n(source: string): boolean {
  return source.includes("useT()") || /\bt\("/.test(source);
}

function componentFiles(): Array<[string, string]> {
  return Object.entries(COMPONENTS)
    .map(([path, source]): [string, string] => [
      path.replace(/^\.\.\//, ""),
      source,
    ])
    .filter(
      ([file]) =>
        !file.includes(".test.") &&
        !file.includes("__tests__/") &&
        !file.startsWith("test/") &&
        !file.startsWith("i18n/"),
    );
}

describe("F4: the copy register", () => {
  it("every {placeholder} exists in both locales", () => {
    const broken: string[] = [];
    for (const key of Object.keys(en) as Array<keyof typeof en>) {
      const holes = (text: string) =>
        [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
      const enHoles = holes(en[key]).join(",");
      const trHoles = holes(tr[key]).join(",");
      if (enHoles !== trHoles) {
        broken.push(`${key}: en has [${enHoles}], tr has [${trHoles}]`);
      }
    }
    expect(broken, broken.join("; ")).toEqual([]);
  });

  it("no locale ships an empty string", () => {
    for (const catalogue of [en, tr]) {
      for (const [key, value] of Object.entries(catalogue)) {
        expect(value.trim(), `${key} is empty`).not.toBe("");
      }
    }
  });

  it("a new component may not ship raw English (baseline shrink-only)", () => {
    const offenders: string[] = [];
    for (const [file, source] of componentFiles()) {
      if (!speaksThroughI18n(source) && !_UNTRANSLATED_BASELINE.has(file)) {
        offenders.push(file);
      }
    }
    expect(
      offenders,
      "new components must speak through the i18n layer (useT/t): " +
        offenders.join(", "),
    ).toEqual([]);
  });

  it("a migrated component leaves the baseline", () => {
    const stale: string[] = [];
    for (const [file, source] of componentFiles()) {
      if (speaksThroughI18n(source) && _UNTRANSLATED_BASELINE.has(file)) {
        stale.push(file);
      }
    }
    expect(
      stale,
      `remove from _UNTRANSLATED_BASELINE so the shrink is on the record: ${stale.join(", ")}`,
    ).toEqual([]);
  });
});
