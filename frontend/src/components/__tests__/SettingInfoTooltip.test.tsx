/**
 * "Current" has to mean current.
 *
 * `currentImpact` is a static line describing the UN-optimised state (C3:
 * "State: Brief consequence"), not a readout. The tooltip labelled it "Current
 * setting:" unconditionally, so a machine sitting at the recommended value was
 * told it was still at the default — three pixels from the green tick saying the
 * opposite. Reported from the UI on MW3 Texture Streaming Limit.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingInfoTooltip } from "../SettingInfoTooltip";
import type { Setting } from "../../types/setting";

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "game_config:mw3:texture_streaming" as `${string}:${string}`,
    module: "game_config",
    name: "mw3:texture_streaming",
    displayName: "MW3 Texture Streaming Limit",
    description: "Caps the bandwidth MW3 spends downloading textures.",
    category: "game_config",
    valueType: "choice",
    choices: ["default", "minimal"],
    defaultValue: "default",
    recommendedValue: "minimal",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "1024 MB: Textures download over HTTP mid-match",
    recommendedImpact: "0 MB: The connection carries only the match",
    impactCategories: [],
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "minimal",
    status: "optimal",
    executionStatus: "idle",
    isOptimized: true,
    isApplicable: true,
    ...overrides,
  };
}

// Radix opens the tooltip on focus as well as hover, and focus is the path that
// works under jsdom. Content is portalled and rendered twice (visible + the
// aria-live copy), so every assertion uses getAllByText.
async function open(setting: Setting) {
  const view = render(<SettingInfoTooltip setting={setting} />);
  await userEvent.tab();
  await screen.findAllByText(setting.description);
  return view;
}

function textOnce(label: string): number {
  return screen.queryAllByText(label).length;
}

describe("SettingInfoTooltip", () => {
  it("labels the achieved state as Current when the setting is optimal", async () => {
    await open(makeSetting({ isOptimized: true }));

    expect(textOnce("Current:")).toBeGreaterThan(0);
    // The exact contradiction reported: an optimal setting must not be
    // described as still downloading over HTTP under a "Current" heading.
    expect(textOnce("Current setting:")).toBe(0);
    // Optimal -> the recommended line is the one that is true right now.
    expect(textOnce("0 MB: The connection carries only the match")).toBeGreaterThan(0);
  });

  it("shows the un-optimised line as Current when the setting has drifted", async () => {
    await open(makeSetting({ isOptimized: false, currentValue: "default" }));

    expect(textOnce("Current:")).toBeGreaterThan(0);
    expect(textOnce("Recommended:")).toBeGreaterThan(0);
    expect(textOnce("If reverted:")).toBe(0);
    expect(textOnce("1024 MB: Textures download over HTTP mid-match")).toBeGreaterThan(0);
  });

  it("drops the case-for-changing once there is nothing to change", async () => {
    // Verbosity follows actionability: effect, its numbers and the sources are
    // the argument for applying, and an already-applied setting is not asking
    // for one.
    await open(
      makeSetting({
        isOptimized: true,
        effect: "Stops mid-match texture downloads",
        sources: ["https://hone.gg/blog/stop-and-fix-packet-burst-in-warzone/"],
      }),
    );

    expect(textOnce("Effect:")).toBe(0);
    expect(textOnce("Sources:")).toBe(0);
    expect(textOnce("1024 MB: Textures download over HTTP mid-match")).toBe(0);
  });

  it("keeps the full case while the setting still needs applying", async () => {
    await open(
      makeSetting({
        isOptimized: false,
        effect: "Stops mid-match texture downloads",
        sources: ["https://hone.gg/blog/stop-and-fix-packet-burst-in-warzone/"],
      }),
    );

    expect(textOnce("Effect:")).toBeGreaterThan(0);
    expect(textOnce("Sources:")).toBeGreaterThan(0);
  });

  it("keeps the how-to on an advisory setting even when it reads OK", async () => {
    // Advisory settings have no Apply button, so this block is the only place
    // that tells the user what to do about it.
    await open(
      makeSetting({
        isOptimized: true,
        isReadonly: true,
        effect: "Enable Resizable BAR in the UEFI setup",
        sources: ["https://example.com/rebar"],
      }),
    );

    expect(textOnce("How to change:")).toBeGreaterThan(0);
    expect(textOnce("Sources:")).toBeGreaterThan(0);
  });
});
