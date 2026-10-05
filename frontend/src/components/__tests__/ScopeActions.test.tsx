/**
 * Apply, Undo and Windows default keep one place and one rule on every page.
 *
 * The group used to vanish when a scope had nothing to do, so the buttons were
 * in one spot on a busy card and absent on a finished one, and a reader could not
 * tell "nothing to do" from "this page has no such button".
 */

import { describe, it, expect, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { fireEvent, render, screen, within } from "../../test/utils";
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
  it("still draws Apply, and keeps Windows default in the menu, each saying why it is idle", () => {
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
    fireEvent.click(screen.getByRole("button", { name: "More actions: Network" }));
    const reset = screen.getByRole("menuitem", {
      name: "Windows default: already at the Windows default in Network",
    });
    expect(reset).toHaveAttribute("aria-disabled", "true");
    // The reason is also the tooltip, for a pointer user.
    expect(apply).toHaveAttribute("title", "Apply: nothing to apply in Network");
  });

  it("is drawn for an empty scope too, so the page header never shifts", () => {
    render(<ScopeActions settings={[]} name="Network" />);

    // Apply and the "more" trigger: the same two controls as for a busy scope.
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

describe("ScopeActions: Undo is the visible way back, Windows default is in the menu", () => {
  const away = setting({ id: "system:a", originalValue: "on", defaultValue: "on", currentValue: "off" });

  it("draws Undo beside Apply only when a recorded original exists", () => {
    const { unmount } = render(<ScopeActions settings={[setting({ id: "system:a" })]} name="Network" />);
    expect(screen.queryByRole("button", { name: /^Undo/ })).not.toBeInTheDocument();
    unmount();

    render(<ScopeActions settings={[away]} name="Network" />);
    expect(screen.getByRole("button", { name: "Undo 1 tweaks: Network" })).toBeEnabled();
  });

  it("never offers Windows default as a button of its own", () => {
    render(<ScopeActions settings={[away]} name="Network" />);

    expect(screen.queryByRole("button", { name: /Windows default/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem")).not.toBeInTheDocument();
  });

  it("reaches Windows default by keyboard alone, with the same confirmation", async () => {
    const user = userEvent.setup();
    render(<ScopeActions settings={[away]} name="Network" />);

    const trigger = screen.getByRole("button", { name: "More actions: Network" });
    trigger.focus();
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.keyboard("{ArrowDown}");
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const item = screen.getByRole("menuitem", {
      name: "Return 1 settings to the Windows default: Network",
    });
    expect(item).toHaveFocus();

    await user.keyboard("{Enter}");
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("1 settings will return to Windows defaults.");
    // The question is the same one every Windows default asks, and answered the same way.
    expect(within(dialog).getByRole("button", { name: "Windows default" })).toBeInTheDocument();
  });

  it("does not merge the two promises: the menu item asks for the reset, never the undo", async () => {
    const user = userEvent.setup();
    render(<ScopeActions settings={[away]} name="Network" />);

    await user.click(screen.getByRole("button", { name: "More actions: Network" }));
    await user.click(screen.getByRole("menuitem", { name: /Windows default/ }));

    expect(screen.getByRole("dialog")).toHaveTextContent("Windows defaults");
    expect(screen.getByRole("dialog")).not.toHaveTextContent("before fpstune");
  });
});
