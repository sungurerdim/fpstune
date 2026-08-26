/**
 * Tests for TweakSetting component.
 * Tests rendering of key states: optimal, suboptimal, loading, disabled.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TweakSetting } from "../TweakSetting";
import type { Setting } from "../../types/setting";

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "timer:hpet" as `${string}:${string}`,
    module: "timer",
    name: "hpet",
    displayName: "HPET",
    description: "High Precision Event Timer. Controls system timer source.",
    category: "core",
    valueType: "choice",
    choices: ["enabled", "disabled"],
    defaultValue: "enabled",
    recommendedValue: "disabled",
    requiresReboot: false,
    isAction: false,
    scope: "essential",
    currentImpact: "Enabled: higher latency",
    recommendedImpact: "Disabled: lower latency",
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "enabled",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
    ...overrides,
  };
}

const defaultProps = {
  isPending: false,
  isModuleLoading: false,
  onApplyValue: vi.fn(),
  onReset: vi.fn(),
};

describe("TweakSetting", () => {
  it("renders setting display name", () => {
    const setting = makeSetting();
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.getByText("HPET")).toBeInTheDocument();
  });

  it("shows loading spinner when status=loading and currentValue=null", () => {
    const setting = makeSetting({
      status: "loading",
      currentValue: null,
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    // Should show a spinner — no control rendered
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("shows value labels (Default, Current, Target) when detected", () => {
    const setting = makeSetting({
      currentValue: "enabled",
      status: "suboptimal",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Target")).toBeInTheDocument();
  });

  it("does not show value labels during initial loading", () => {
    const setting = makeSetting({ status: "loading", currentValue: null });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.queryByText("Default")).not.toBeInTheDocument();
    expect(screen.queryByText("Current")).not.toBeInTheDocument();
  });

  it("shows N/A when setting is not applicable", () => {
    const setting = makeSetting({
      isApplicable: false,
      currentValue: "enabled",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.getByText("N/A")).toBeInTheDocument();
  });

  it("shows the Windows-default button when setting is suboptimal", () => {
    const setting = makeSetting({ isOptimized: false, currentValue: "enabled" });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    const resetBtn = screen.getByRole("button", { name: /restore the windows default/i });
    expect(resetBtn).toBeInTheDocument();
  });

  it("does not show the Windows-default button when setting is already optimal", () => {
    const setting = makeSetting({
      isOptimized: true,
      currentValue: "disabled",
      status: "optimal",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(
      screen.queryByRole("button", { name: /restore the windows default/i }),
    ).not.toBeInTheDocument();
  });

  it("calls onReset when the Windows-default button is clicked", async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    const setting = makeSetting({ isOptimized: false, currentValue: "enabled" });
    render(
      <TweakSetting setting={setting} {...defaultProps} onReset={onReset} />,
    );

    const resetBtn = screen.getByRole("button", { name: /restore the windows default/i });
    await user.click(resetBtn);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("shows Verify button when onVerify prop is provided", () => {
    const setting = makeSetting({ currentValue: "enabled" });
    render(
      <TweakSetting
        setting={setting}
        {...defaultProps}
        onVerify={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /verify current value/i }),
    ).toBeInTheDocument();
  });

  it("calls onVerify when Verify button is clicked", async () => {
    const user = userEvent.setup();
    const onVerify = vi.fn();
    const setting = makeSetting({ currentValue: "enabled" });
    render(
      <TweakSetting setting={setting} {...defaultProps} onVerify={onVerify} />,
    );

    await user.click(
      screen.getByRole("button", { name: /verify current value/i }),
    );
    expect(onVerify).toHaveBeenCalledTimes(1);
  });

  it("shows RISK badge for advanced risk settings with riskWarning", () => {
    const setting = makeSetting({
      riskLevel: "advanced",
      riskWarning: "May cause instability on some systems.",
      currentValue: "enabled",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.getByText("RISK")).toBeInTheDocument();
    // "ADV" read as "Advisory", which is a different state in the same row
    // (detect-only, no Apply button). The label must not come back.
    expect(screen.queryByText("ADV")).not.toBeInTheDocument();
  });

  it("shows a warning for moderate risk too, not only advanced", () => {
    // 29 shipped settings carry a riskWarning at moderate/low. The badge was
    // gated on riskLevel === "advanced", so every one of those warnings was
    // written and then never rendered to anyone.
    const setting = makeSetting({
      riskLevel: "moderate",
      riskWarning: "Reverts on driver update.",
      currentValue: "enabled",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    const badge = screen.getByTestId("risk-warning-badge");
    expect(badge).toHaveAttribute("data-risk", "moderate");
    expect(badge).toHaveAttribute("title", "Reverts on driver update.");
  });

  it("shows no risk badge when the setting carries no warning", () => {
    const setting = makeSetting({ riskLevel: "low", currentValue: "enabled" });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.queryByTestId("risk-warning-badge")).not.toBeInTheDocument();
  });

  it("shows (R) badge for settings that require reboot", () => {
    const setting = makeSetting({ requiresReboot: true, currentValue: "enabled" });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.getByText("(R)")).toBeInTheDocument();
  });

  it("shows lastError when present", () => {
    const setting = makeSetting({
      currentValue: "enabled",
      lastError: "Permission denied: registry key locked",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(
      screen.getByText("Permission denied: registry key locked"),
    ).toBeInTheDocument();
  });

  it("renders PillSelector for choice settings with 3+ options", () => {
    const setting = makeSetting({
      valueType: "choice",
      choices: ["low", "medium", "high"],
      currentValue: "low",
      recommendedValue: "high",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    // PillSelector renders the choice options as buttons; "low" also appears as Current value text
    expect(screen.getAllByText("low").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: "medium" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "high" })).toBeInTheDocument();
  });

  it("shows checkbox when onSelect prop is provided", () => {
    const setting = makeSetting({ currentValue: "enabled" });
    render(
      <TweakSetting
        setting={setting}
        {...defaultProps}
        onSelect={vi.fn()}
        isSelected={false}
      />,
    );
    expect(
      screen.getByRole("checkbox", { name: /select hpet/i }),
    ).toBeInTheDocument();
  });

  it("shows selected state on checkbox when isSelected=true", () => {
    const setting = makeSetting({ currentValue: "enabled" });
    render(
      <TweakSetting
        setting={setting}
        {...defaultProps}
        onSelect={vi.fn()}
        isSelected={true}
      />,
    );
    const checkbox = screen.getByRole("checkbox", { name: /select hpet/i });
    expect(checkbox).toBeChecked();
  });

  it("shows operationStatus 'queued' badge", () => {
    const setting = makeSetting({ currentValue: "enabled" });
    render(
      <TweakSetting
        setting={setting}
        {...defaultProps}
        operationStatus="queued"
      />,
    );
    expect(screen.getByText("queued")).toBeInTheDocument();
  });

  it("shows readonly 'OK' badge when optimal and isReadonly=true", () => {
    const setting = makeSetting({
      isReadonly: true,
      isOptimized: true,
      currentValue: "disabled",
      status: "optimal",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("shows readonly 'Advisory' badge when suboptimal and isReadonly=true", () => {
    const setting = makeSetting({
      isReadonly: true,
      isOptimized: false,
      currentValue: "enabled",
      status: "suboptimal",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.getByText("Advisory")).toBeInTheDocument();
  });
});

describe("the row's switch carries the row's name", () => {
  /**
   * The ToggleSwitch primitive gives every call site role="switch" and
   * aria-checked, but the name is the caller's job — and these rows passed
   * none, so a screen reader heard thirty anonymous switches on a fresh
   * machine with no way to tell which one moves the CPU's minimum clock.
   */

  it("names a two-choice setting's switch by its visible label", () => {
    render(<TweakSetting setting={makeSetting()} {...defaultProps} />);

    // Role AND name: a bare getByRole("switch") passed on the unnamed version.
    expect(screen.getByRole("switch", { name: "HPET" })).toBeInTheDocument();
  });

  it("names an int setting's switch", () => {
    const setting = makeSetting({
      valueType: "int",
      choices: [],
      displayName: "Minimum Processor State",
      defaultValue: 5,
      recommendedValue: 5,
      currentValue: 100,
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);

    expect(
      screen.getByRole("switch", { name: "Minimum Processor State" }),
    ).toBeInTheDocument();
  });

  it("names a bool setting's switch", () => {
    const setting = makeSetting({
      valueType: "bool",
      choices: [],
      displayName: "Hardware-Accelerated GPU Scheduling",
      defaultValue: false,
      recommendedValue: true,
      currentValue: false,
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);

    expect(
      screen.getByRole("switch", { name: "Hardware-Accelerated GPU Scheduling" }),
    ).toBeInTheDocument();
  });
});

describe("TweakSetting undo", () => {
  /**
   * "Restore the Windows default" and "undo fpstune's change" are different
   * promises. On a machine that deliberately ran a non-stock value, the first
   * discards the user's own configuration — which is why the row offers both,
   * and why undo appears only when there is genuinely something to undo.
   */

  it("offers undo when the machine held something else before", () => {
    const setting = makeSetting({
      currentValue: "disabled",
      originalValue: "enabled",
    });
    render(
      <TweakSetting setting={setting} {...defaultProps} onUndo={vi.fn()} />,
    );

    expect(
      screen.getByRole("button", { name: /undo fpstune's change/i }),
    ).toBeInTheDocument();
  });

  it("names the value it would restore, so the action is not a leap of faith", () => {
    const setting = makeSetting({
      currentValue: "disabled",
      originalValue: "enabled",
    });
    render(
      <TweakSetting setting={setting} {...defaultProps} onUndo={vi.fn()} />,
    );

    expect(
      screen.getByRole("button", { name: /back to enabled/i }),
    ).toBeInTheDocument();
  });

  it("hides undo when nothing was recorded", () => {
    // A machine fpstune has not scanned yet has no original for this setting,
    // and the endpoint answers 409 rather than quietly doing a reset — so the
    // row must not offer an action that cannot succeed.
    const setting = makeSetting({ currentValue: "disabled" });
    render(
      <TweakSetting setting={setting} {...defaultProps} onUndo={vi.fn()} />,
    );

    expect(
      screen.queryByRole("button", { name: /undo fpstune's change/i }),
    ).not.toBeInTheDocument();
  });

  it("hides undo when the setting is already where it started", () => {
    // Nothing to undo. Offering it would either be a no-op or, worse, read as
    // "fpstune changed this" about a setting it left alone.
    const setting = makeSetting({
      currentValue: "enabled",
      originalValue: "enabled",
    });
    render(
      <TweakSetting setting={setting} {...defaultProps} onUndo={vi.fn()} />,
    );

    expect(
      screen.queryByRole("button", { name: /undo fpstune's change/i }),
    ).not.toBeInTheDocument();
  });

  it("hides undo when the row was given no undo handler", () => {
    const setting = makeSetting({
      currentValue: "disabled",
      originalValue: "enabled",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);

    expect(
      screen.queryByRole("button", { name: /undo fpstune's change/i }),
    ).not.toBeInTheDocument();
  });

  it("calls onUndo when clicked", async () => {
    const user = userEvent.setup();
    const onUndo = vi.fn();
    const setting = makeSetting({
      currentValue: "disabled",
      originalValue: "enabled",
    });
    render(
      <TweakSetting setting={setting} {...defaultProps} onUndo={onUndo} />,
    );

    await user.click(
      screen.getByRole("button", { name: /undo fpstune's change/i }),
    );
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it("undo and the Windows default are separate actions on the same row", () => {
    // The distinction is the whole point: they disagree exactly when the user
    // had configured something themselves.
    const setting = makeSetting({
      currentValue: "disabled",
      originalValue: "something the user chose",
      defaultValue: "enabled",
      isOptimized: false,
    });
    render(
      <TweakSetting setting={setting} {...defaultProps} onUndo={vi.fn()} />,
    );

    expect(
      screen.getByRole("button", { name: /undo fpstune's change/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /restore the windows default/i }),
    ).toBeInTheDocument();
  });
});
