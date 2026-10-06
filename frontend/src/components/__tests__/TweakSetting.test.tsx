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
    domain: "software",
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

  it("shows Verify button when onVerify prop is provided", () => {
    const setting = makeSetting({ currentValue: "enabled" });
    render(
      <TweakSetting setting={setting} {...defaultProps} onVerify={vi.fn()} />,
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

  it("states what an advisory found, not only that it is one", () => {
    // The Software Tweaks row showed a bare "Advisory" badge for a detect-only
    // setting. The row must state the current state — here the machine's own
    // numbers — on this surface as on Home.
    const setting = makeSetting({
      id: "network:19:link_capability" as `${string}:${string}`,
      isReadonly: true,
      choices: ["at_capability", "below_capability"],
      currentValue: "below_capability",
      recommendedValue: "at_capability",
      isOptimized: false,
      status: "suboptimal",
      finding: { kind: "link_speed", linked_mbps: 100, ceiling_mbps: 2500 },
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.getByText("Advisory")).toBeInTheDocument();
    expect(screen.getByTestId("setting-value-state")).toHaveTextContent(
      "Link running at 100 Mbps; the adapter supports 2.5 Gbps.",
    );
    expect(screen.queryByText(/below_capability/)).not.toBeInTheDocument();
  });

  it("badges an advisory that read nothing as not read, never as a finding", () => {
    const setting = makeSetting({
      id: "system:thermal_condition" as `${string}:${string}`,
      isReadonly: true,
      currentValue: null,
      recommendedValue: "ok",
      isOptimized: false,
      status: "suboptimal",
    });
    render(<TweakSetting setting={setting} {...defaultProps} />);
    expect(screen.getByText("Not read")).toBeInTheDocument();
    expect(screen.queryByText("Advisory")).not.toBeInTheDocument();
    expect(screen.queryByText("OK")).not.toBeInTheDocument();
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
    const setting = makeSetting({
      requiresReboot: true,
      currentValue: "enabled",
    });
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
      screen.getByRole("switch", {
        name: "Hardware-Accelerated GPU Scheduling",
      }),
    ).toBeInTheDocument();
  });
});

describe("TweakSetting reset to default", () => {
  /**
   * One way back on every row: the setting's own default, named by its domain.
   * It is drawn whenever the value differs from that default — including a row
   * already at its recommended value, which is exactly the one a user wants to
   * take back — and never when there is nothing to write.
   */
  const away = { currentValue: "disabled", defaultValue: "enabled" } as const;

  it("draws one visible button that names the Windows default and the value it writes", () => {
    render(<TweakSetting setting={makeSetting(away)} {...defaultProps} />);

    const reset = screen.getByRole("button", {
      name: "Reset HPET to default: Windows default (enabled)",
    });
    expect(reset).toBeEnabled();
    // No overflow menu behind it: the visible button is the only way back.
    expect(screen.queryByRole("button", { name: "More actions" })).not.toBeInTheDocument();
  });

  it.each([
    ["hardware", "Driver default"],
    ["game", "Game default"],
    ["software", "Windows default"],
  ] as const)("names the %s default as %s", (domain, word) => {
    render(<TweakSetting setting={makeSetting({ ...away, domain })} {...defaultProps} />);

    expect(
      screen.getByRole("button", { name: `Reset HPET to default: ${word} (enabled)` }),
    ).toBeInTheDocument();
  });

  it("shows the default it will write in its tooltip", async () => {
    const user = userEvent.setup();
    render(<TweakSetting setting={makeSetting(away)} {...defaultProps} />);

    await user.hover(
      screen.getByRole("button", { name: /^Reset HPET to default/ }),
    );
    expect(
      (await screen.findAllByText("Reset to default: Windows default (enabled)")).length,
    ).toBeGreaterThan(0);
  });

  it("stays drawn on a row already at its recommended value, when that is not the default", () => {
    render(
      <TweakSetting
        setting={makeSetting({ ...away, isOptimized: true, status: "optimal" })}
        {...defaultProps}
      />,
    );

    expect(screen.getByRole("button", { name: /^Reset HPET to default/ })).toBeInTheDocument();
  });

  it("is hidden when the value already is the default, so it never writes nothing", () => {
    render(
      <TweakSetting
        setting={makeSetting({ currentValue: "enabled", defaultValue: "enabled" })}
        {...defaultProps}
      />,
    );

    expect(screen.queryByRole("button", { name: /^Reset HPET/ })).not.toBeInTheDocument();
  });

  it("is hidden for an advisory, which fpstune can read and cannot write", () => {
    render(<TweakSetting setting={makeSetting({ ...away, isReadonly: true })} {...defaultProps} />);

    expect(screen.queryByRole("button", { name: /^Reset HPET/ })).not.toBeInTheDocument();
  });

  it("calls onReset when pressed, by pointer", async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    render(<TweakSetting setting={makeSetting(away)} {...defaultProps} onReset={onReset} />);

    await user.click(screen.getByRole("button", { name: /^Reset HPET to default/ }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("calls onReset when focused and activated with the keyboard", async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    render(<TweakSetting setting={makeSetting(away)} {...defaultProps} onReset={onReset} />);

    screen.getByRole("button", { name: /^Reset HPET to default/ }).focus();
    await user.keyboard("{Enter}");

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("is disabled while the row is busy", () => {
    render(<TweakSetting setting={makeSetting(away)} {...defaultProps} isPending />);

    expect(screen.getByRole("button", { name: /^Reset HPET to default/ })).toBeDisabled();
  });
});
