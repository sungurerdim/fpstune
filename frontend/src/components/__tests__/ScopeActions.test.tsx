/**
 * Apply and Reset to default keep one place and one rule on every page.
 *
 * The group used to vanish when a scope had nothing to do, so the buttons were
 * in one spot on a busy card and absent on a finished one, and a reader could not
 * tell "nothing to do" from "this page has no such button".
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, within } from "../../test/utils";
import { ScopeActions } from "../ScopeActions";
import type { Setting } from "../../types/setting";

const run = vi.fn();

vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({ run, stop: vi.fn(), isRunning: false }),
}));

beforeEach(() => run.mockReset());

function setting(over: Partial<Setting> & { id: string }): Setting {
  return {
    module: "system",
    name: "x",
    displayName: "A Tweak",
    description: "Does a thing.",
    category: "system",
    valueType: "choice",
    choices: ["off", "on"],
    defaultValue: "off",
    recommendedValue: "on",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "off",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    domain: "software",
    effect: "",
    ...over,
  } as Setting;
}

describe("ScopeActions with nothing to act on", () => {
  it("still draws Apply and Reset to default, each saying why it is idle", () => {
    const atIdeal = setting({
      id: "system:fine",
      currentValue: "on",
      defaultValue: "on",
      status: "optimal",
      isOptimized: true,
    });
    render(<ScopeActions settings={[atIdeal]} name="Network" />);

    const apply = screen.getByRole("button", { name: "Apply: nothing to apply in Network" });
    expect(apply).toBeDisabled();
    const reset = screen.getByRole("button", {
      name: "Reset to default: everything in Network is already at its default",
    });
    expect(reset).toBeDisabled();
    // The reason is also the tooltip, for a pointer user.
    expect(apply).toHaveAttribute("title", "Apply: nothing to apply in Network");
    expect(reset).toHaveAttribute(
      "title",
      "Reset to default: everything in Network is already at its default",
    );
  });

  it("is drawn for an empty scope too, so the page header never shifts", () => {
    render(<ScopeActions settings={[]} name="Network" />);

    // Apply and Reset to default: the same two controls as for a busy scope.
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("enables Apply with its count once something is away from its recommended value", () => {
    render(<ScopeActions settings={[setting({ id: "system:a" })]} name="Network" />);

    expect(screen.getByRole("button", { name: "Apply 1 tweaks: Network" })).toBeEnabled();
  });

  it("keeps Home's Apply-only group to Apply only, still disabled when idle", () => {
    render(<ScopeActions settings={[]} name="Network" only={["apply"]} />);

    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: /^Apply:/ })).toBeDisabled();
  });
});

describe("ScopeActions: Reset to default is the one visible way back", () => {
  // Away from its own default; the recommended value is something else again.
  const away = setting({ id: "system:a", defaultValue: "default", currentValue: "off" });

  it("draws one enabled Reset to default beside Apply, with no overflow menu", () => {
    render(<ScopeActions settings={[away]} name="Network" />);

    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /^More actions/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reset 1 settings to the Windows default: Network" }),
    ).toBeEnabled();
  });

  it.each([
    ["software", "Windows"],
    ["hardware", "driver"],
    ["game", "game"],
  ] as const)("names the %s scope's default in its accessible name and tooltip", (domain, word) => {
    render(<ScopeActions settings={[setting({ ...away, domain })]} name="Scope" />);

    const reset = screen.getByRole("button", {
      name: `Reset 1 settings to the ${word} default: Scope`,
    });
    expect(reset).toHaveAttribute("title", `Reset 1 settings to the ${word} default: Scope`);
    expect(reset).toHaveTextContent("Reset to default (1)");
  });

  it("says so when a scope mixes domains", () => {
    render(
      <ScopeActions
        settings={[away, setting({ ...away, id: "gpu:b", domain: "hardware" })]}
        name="Scope"
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "Reset 2 settings to their own defaults (Windows, driver or game): Scope",
      }),
    ).toBeEnabled();
  });

  it("does not count an advisory, which fpstune can read and cannot write", () => {
    render(<ScopeActions settings={[setting({ ...away, isReadonly: true })]} name="Network" />);

    expect(
      screen.getByRole("button", {
        name: "Reset to default: everything in Network is already at its default",
      }),
    ).toBeDisabled();
  });

  it("asks first, by keyboard alone, naming the count, then resets the ids", async () => {
    const user = userEvent.setup();
    render(<ScopeActions settings={[away]} name="Network" />);

    const reset = screen.getByRole("button", {
      name: "Reset 1 settings to the Windows default: Network",
    });
    reset.focus();
    await user.keyboard("{Enter}");

    expect(run).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("1 settings will return to their defaults.");
    expect(dialog).toHaveTextContent("what Windows ships");
    await user.click(within(dialog).getByRole("button", { name: "Reset to default" }));

    expect(run).toHaveBeenCalledWith("reset", ["system:a"]);
  });
});
