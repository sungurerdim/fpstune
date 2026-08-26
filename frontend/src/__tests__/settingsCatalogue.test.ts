/**
 * F2/F3: the setting-copy edge catalogue.
 *
 * Each test names the failure it guards against:
 * - a Turkish user shown English for a setting the catalogue translates;
 * - a per-adapter id (network:<index>:eee) missing its translation because the
 *   machine-specific interface index can never be a catalogue key (C9);
 * - a machine-derived description (panel ceilings, VRAM budgets) frozen into
 *   the static catalogue — the empty-description entries MUST fall through to
 *   the backend's per-machine English text, so `??` instead of `||` in the
 *   helper is a real bug, not a style choice;
 * - a catalogue entry whose name is empty, which would render a blank row.
 */

import { describe, it, expect, afterEach } from "vitest";
import { setLocale } from "../i18n";
import { localizedDescription, localizedName } from "../i18n/settings";
import { settingsTr } from "../i18n/settingsTr";
import type { Setting } from "../types/setting";

function makeSetting(overrides: Partial<Setting>): Setting {
  return {
    id: "power:cpu_boost",
    shortName: "CPU turbo boost",
    displayName: "Processor Performance Boost Mode",
    description: "Controls how the CPU enters its boost clocks.",
    ...overrides,
  } as unknown as Setting;
}

afterEach(() => setLocale("en"));

describe("F2/F3: the setting-copy edge catalogue", () => {
  it("English locale always returns the backend copy untouched", () => {
    setLocale("en");
    const setting = makeSetting({});
    expect(localizedName(setting)).toBe("CPU turbo boost");
    expect(localizedDescription(setting)).toBe(
      "Controls how the CPU enters its boost clocks.",
    );
  });

  it("Turkish locale resolves a direct catalogue id", () => {
    setLocale("tr");
    const entry = settingsTr["power:cpu_boost"];
    expect(entry).toBeDefined();
    const setting = makeSetting({});
    expect(localizedName(setting)).toBe(entry.name);
    expect(localizedDescription(setting)).toBe(entry.description);
  });

  it("a per-adapter id resolves through its stable last segment", () => {
    // The interface index is this machine's fact and must never be a key in
    // source (C9) — the catalogue holds `network:*:eee` and every index maps
    // onto it.
    setLocale("tr");
    const wildcard = settingsTr["network:*:eee"];
    expect(wildcard).toBeDefined();
    const setting = makeSetting({
      id: "network:17:eee",
      shortName: "Energy-saving Ethernet",
      displayName: "Energy Efficient Ethernet (Realtek 2.5GbE)",
    });
    expect(localizedName(setting)).toBe(wildcard.name);
    expect(localizedDescription(setting)).toBe(wildcard.description);
  });

  it("a machine-derived description stays English: empty TR falls through", () => {
    // These entries carry name-only translations on purpose: their English
    // descriptions are composed per machine by the backend (panel refresh
    // ceiling, VRAM budget), so a static Turkish sentence would freeze one
    // machine's numbers into source.
    setLocale("tr");
    const entry = settingsTr["game_config:mw4:vram_scale"];
    expect(entry).toBeDefined();
    expect(entry.description).toBe("");
    const setting = makeSetting({
      id: "game_config:mw4:vram_scale",
      description: "Composed on this machine from the detected VRAM.",
    });
    expect(localizedName(setting)).toBe(entry.name);
    expect(localizedDescription(setting)).toBe(
      "Composed on this machine from the detected VRAM.",
    );
  });

  it("an id the catalogue does not know falls back to English, visibly", () => {
    setLocale("tr");
    const setting = makeSetting({
      id: "system:not_in_catalogue",
      shortName: "Some new tweak",
      description: "English body.",
    });
    expect(localizedName(setting)).toBe("Some new tweak");
    expect(localizedDescription(setting)).toBe("English body.");
  });

  it("no catalogue entry ships an empty name", () => {
    const blank = Object.entries(settingsTr)
      .filter(([, entry]) => entry.name.trim() === "")
      .map(([id]) => id);
    expect(blank, blank.join(", ")).toEqual([]);
  });
});
