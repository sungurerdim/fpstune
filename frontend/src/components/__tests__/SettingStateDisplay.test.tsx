/**
 * A row has to answer "is this machine already right?" on sight.
 *
 * Before this, rows showed only the value you could change a setting to, so the
 * question the whole product exists to answer could not be read off a row — and
 * the header's "latency tweaks" count could not be traced to the settings that
 * produced it.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  SettingValueState,
  ImpactCategoryTags,
  RiskWarningBadge,
} from "../SettingStateDisplay";
import type { Setting } from "../../types/setting";

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "game_config:mw3:shadow_quality" as `${string}:${string}`,
    module: "game_config",
    name: "mw3:shadow_quality",
    displayName: "MW3 Shadow Quality",
    description: "Shadow detail level.",
    category: "game_config",
    valueType: "choice",
    choices: ["Low", "Normal", "High"],
    defaultValue: "High",
    recommendedValue: "Low",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    impactCategories: [],
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "High",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...overrides,
  };
}

describe("SettingValueState", () => {
  it("shows a tick and the current value when already at the ideal", () => {
    render(
      <SettingValueState
        setting={makeSetting({ currentValue: "Low", isOptimized: true })}
      />,
    );
    const el = screen.getByTestId("setting-value-state");
    expect(el).toHaveAttribute("data-state", "optimal");
    expect(el).toHaveTextContent("Low");
  });

  it("shows current and ideal when drifted", () => {
    render(<SettingValueState setting={makeSetting()} />);
    const el = screen.getByTestId("setting-value-state");
    expect(el).toHaveAttribute("data-state", "drifted");
    // Both ends must be present: showing only the target is what made a row
    // unreadable, and showing only the current gives nothing to act on.
    expect(el).toHaveTextContent("High");
    expect(el).toHaveTextContent("Low");
  });

  it("appends the raw value hint when the game's label differs", () => {
    render(
      <SettingValueState
        setting={makeSetting({
          currentValue: "full",
          recommendedValue: "full",
          isOptimized: true,
          valueHints: { full: "Maximal" },
        })}
      />,
    );
    // "off/min/full" reads as the opposite of what the game calls them, which
    // is exactly how the menu-resolution recommendation ended up inverted.
    expect(screen.getByTestId("setting-value-state")).toHaveTextContent(
      "full (Maximal)",
    );
  });

  it("renders nothing for action settings", () => {
    // Cleanup actions have no current-vs-ideal; an arrow between two booleans
    // would be noise on every maintenance row.
    render(<SettingValueState setting={makeSetting({ isAction: true })} />);
    expect(screen.queryByTestId("setting-value-state")).not.toBeInTheDocument();
  });

  it("renders nothing while the value is still being detected", () => {
    render(
      <SettingValueState
        setting={makeSetting({ status: "loading", currentValue: null })}
      />,
    );
    expect(screen.queryByTestId("setting-value-state")).not.toBeInTheDocument();
  });
});

describe("ImpactCategoryTags", () => {
  it("renders a tag per category", () => {
    render(
      <ImpactCategoryTags
        setting={makeSetting({ impactCategories: ["latency", "fps"] })}
      />,
    );
    expect(screen.getByText("Latency")).toBeInTheDocument();
    expect(screen.getByText("FPS")).toBeInTheDocument();
  });

  it("renders nothing when a setting has no categories", () => {
    render(<ImpactCategoryTags setting={makeSetting()} />);
    expect(screen.queryByTestId("impact-category-tags")).not.toBeInTheDocument();
  });

  it("caps the visible tags and reports how many are hidden", () => {
    render(
      <ImpactCategoryTags
        max={2}
        setting={makeSetting({
          impactCategories: ["latency", "fps", "thermal", "storage"],
        })}
      />,
    );
    expect(screen.getByText("Latency")).toBeInTheDocument();
    expect(screen.getByText("FPS")).toBeInTheDocument();
    expect(screen.queryByText("Thermal")).not.toBeInTheDocument();
    // Silent truncation would read as "this tweak only does two things".
    expect(screen.getByText("+2")).toBeInTheDocument();
  });
});

describe("RiskWarningBadge", () => {
  it("labels advanced risk RISK, never ADV", () => {
    render(
      <RiskWarningBadge
        setting={makeSetting({ riskLevel: "advanced", riskWarning: "Careful." })}
      />,
    );
    expect(screen.getByText("RISK")).toBeInTheDocument();
    expect(screen.queryByText("ADV")).not.toBeInTheDocument();
  });

  it("still renders for a moderate-risk warning", () => {
    render(
      <RiskWarningBadge
        setting={makeSetting({ riskLevel: "moderate", riskWarning: "Note." })}
      />,
    );
    expect(screen.getByTestId("risk-warning-badge")).toHaveTextContent("NOTE");
  });

  it("renders nothing without a warning", () => {
    render(<RiskWarningBadge setting={makeSetting()} />);
    expect(screen.queryByTestId("risk-warning-badge")).not.toBeInTheDocument();
  });
});
