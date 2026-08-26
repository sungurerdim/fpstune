/**
 * The parts of this UI that a screen reader or a keyboard has to be able to use.
 *
 * These are asserted rather than eyeballed because the two defects below both
 * look completely fine on screen, and that is exactly why they survive:
 *
 * *A list of identical buttons.* Home renders one row per setting that needs
 * changing — thirty of them on a fresh machine — each with a button labelled
 * "Apply". Sighted, the row above it says which setting. Read aloud, it is
 * "Apply, Apply, Apply", and there is no way to tell which one is about to
 * change the CPU's minimum clock.
 *
 * *State carried only by colour.* A row that is already at its recommended
 * value shows a green tick; one that is not shows a red arrow. The tick is
 * `aria-hidden` and the colour is CSS, so the single most important fact about
 * a row — is this machine already right? — reaches a screen reader as nothing
 * at all. It is also the fact a red/green colour-blind user cannot see.
 *
 * jsdom has no layout and no computed colours, so contrast is not checkable
 * here and is not pretended to be — that needs a real browser and is recorded
 * as an open gap rather than asserted away.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TweakListRow } from "../TweakListRow";
import { SettingValueState } from "../SettingStateDisplay";
import type { Setting } from "../../types/setting";

vi.mock("../../hooks/useApplySingle", () => ({
  useApplySingle: () => ({ applySingle: vi.fn(), isPending: () => false }),
}));

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "power:cpu_min_state" as `${string}:${string}`,
    module: "power",
    name: "cpu_min_state",
    displayName: "Minimum Processor State",
    description: "Lowest clock speed the CPU is allowed to drop to when idle.",
    category: "power",
    valueType: "int",
    choices: [],
    defaultValue: 5,
    recommendedValue: 5,
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    impactCategories: ["thermal"],
    categoryOrder: 13,
    riskLevel: "low",
    evidenceLevel: "proven",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: 100,
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...overrides,
  };
}

describe("every control says what it acts on", () => {
  it("names the setting in the row's Apply button", () => {
    render(<TweakListRow setting={makeSetting()} />);

    // Queried by accessible name, which is what assistive tech actually reads —
    // a `getByText("Apply")` would pass on the broken version.
    expect(
      screen.getByRole("button", { name: "Apply Minimum Processor State" }),
    ).toBeInTheDocument();
  });

  it("distinguishes two rows' buttons from each other", () => {
    render(
      <>
        <TweakListRow setting={makeSetting()} />
        <TweakListRow
          setting={makeSetting({
            id: "power:cpu_idle_states" as `${string}:${string}`,
            displayName: "CPU Idle States",
          })}
        />
      </>,
    );

    const names = screen
      .getAllByRole("button")
      .map((button) => button.getAttribute("aria-label") ?? button.textContent);

    expect(new Set(names).size).toBe(names.length);
  });
});

describe("state is readable without seeing colour", () => {
  it("says a setting is already at its recommended value", () => {
    const { container } = render(
      <SettingValueState setting={makeSetting({ isOptimized: true, currentValue: 5 })} />,
    );

    // The tick is decorative; the sentence has to exist somewhere a reader
    // reaches it. `textContent` covers visible text and sr-only alike.
    expect(container.textContent).toMatch(/already|recommended|optimal/i);
  });

  it("says a setting is not, and what it would become", () => {
    const { container } = render(<SettingValueState setting={makeSetting()} />);

    expect(container.textContent).toMatch(/100/);
    expect(container.textContent).toMatch(/5/);
    expect(container.textContent).toMatch(/change|recommend|instead|to /i);
  });
});

describe("keyboard order is the reading order", () => {
  it("uses no positive tabindex", () => {
    // A positive tabindex pulls one control to the front of the whole page's
    // tab order, which is invisible until someone tabs through and lands
    // somewhere absurd.
    const { container } = render(<TweakListRow setting={makeSetting()} />);

    const forced = Array.from(container.querySelectorAll("[tabindex]")).filter(
      (element) => Number(element.getAttribute("tabindex")) > 0,
    );

    expect(forced).toEqual([]);
  });

  it("leaves the Apply button reachable", () => {
    render(<TweakListRow setting={makeSetting()} />);

    const button = screen.getByRole("button", {
      name: "Apply Minimum Processor State",
    });

    expect(button).not.toHaveAttribute("tabindex", "-1");
    expect(button).not.toBeDisabled();
  });
});
