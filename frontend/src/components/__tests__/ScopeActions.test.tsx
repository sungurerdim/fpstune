/**
 * Apply, Undo and Windows default keep one place and one rule on every page.
 *
 * The group used to vanish when a scope had nothing to do, so the buttons were
 * in one spot on a busy card and absent on a finished one, and a reader could not
 * tell "nothing to do" from "this page has no such button".
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "../../test/utils";
import { ScopeActions } from "../ScopeActions";
import type { Setting } from "../../types/setting";

vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({ run: vi.fn(), stop: vi.fn(), isRunning: false }),
}));

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
    effect: "",
    ...over,
  } as Setting;
}

describe("ScopeActions with nothing to act on", () => {
  it("still draws Apply and Windows default, disabled, each saying why", () => {
    const atIdeal = setting({
      id: "system:fine",
      currentValue: "on",
      defaultValue: "on",
      status: "optimal",
      isOptimized: true,
    });
    render(<ScopeActions settings={[atIdeal]} name="Network" />);

    const apply = screen.getByRole("button", { name: "Apply: nothing to apply in Network" });
    const reset = screen.getByRole("button", {
      name: "Windows default: already at the Windows default in Network",
    });
    expect(apply).toBeDisabled();
    expect(reset).toBeDisabled();
    // The reason is also the tooltip, for a pointer user.
    expect(apply).toHaveAttribute("title", "Apply: nothing to apply in Network");
  });

  it("is drawn for an empty scope too, so the page header never shifts", () => {
    render(<ScopeActions settings={[]} name="Network" />);

    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("offers no Undo without a recorded original, so it never promises one it cannot keep", () => {
    render(<ScopeActions settings={[setting({ id: "system:a" })]} name="Network" />);

    expect(screen.queryByRole("button", { name: /^Undo/ })).not.toBeInTheDocument();
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
