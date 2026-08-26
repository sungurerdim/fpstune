/**
 * Home's compact row: apply from here, and take it back from here.
 *
 * Undo used to live only on the Settings tab, so a change made from Home could
 * not be undone from Home — the one screen a new user stays on. Whatever the
 * screen, the way back has to be on it.
 *
 * "Undo" and "Reset" are different promises and this row must not blur them.
 * Reset writes the Windows stock value. Undo writes what *this machine* held
 * the first time fpstune saw it, which is only knowable if it was recorded. So
 * the button appears when there is genuinely something to undo and not
 * otherwise: shown without a recorded original it would either do nothing or
 * fall through to a reset, quietly keeping the wrong promise.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TweakListRow } from "../TweakListRow";
import type { Setting } from "../../types/setting";

const applySingle = vi.fn();
const undoSingle = vi.fn();

vi.mock("../../hooks/useApplySingle", () => ({
  useApplySingle: () => ({
    applySingle: (...args: unknown[]) => applySingle(...args),
    undoSingle: (...args: unknown[]) => undoSingle(...args),
    isPending: () => false,
  }),
}));

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "power:cpu_min_state" as `${string}:${string}`,
    module: "power",
    name: "cpu_min_state",
    displayName: "Minimum Processor State",
    description: "Lowest clock the CPU may drop to when idle.",
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
    currentValue: 5,
    status: "optimal",
    executionStatus: "idle",
    isOptimized: true,
    isApplicable: true,
    ...overrides,
  };
}

beforeEach(() => {
  applySingle.mockClear();
  undoSingle.mockClear();
});

const undoButton = () => screen.queryByRole("button", { name: /^Undo fpstune's change/i });

describe("the way back is on the screen you changed it from", () => {
  it("offers undo once fpstune has moved the value away from the original", () => {
    render(<TweakListRow setting={makeSetting({ originalValue: 100, currentValue: 5 })} />);

    expect(undoButton()).toBeInTheDocument();
  });

  it("says in the control's name what undoing would restore", () => {
    render(<TweakListRow setting={makeSetting({ originalValue: 100, currentValue: 5 })} />);

    expect(undoButton()).toHaveAccessibleName(
      "Undo fpstune's change to Minimum Processor State, back to 100",
    );
  });

  it("undoes the setting it is attached to", async () => {
    const setting = makeSetting({ originalValue: 100, currentValue: 5 });
    render(<TweakListRow setting={setting} />);

    await userEvent.click(undoButton()!);

    expect(undoSingle).toHaveBeenCalledWith(setting);
    expect(applySingle).not.toHaveBeenCalled();
  });
});

describe("it never offers an undo it cannot honour", () => {
  it("stays hidden when nothing was recorded before fpstune ran", () => {
    // Without an original, undo would fall through to a reset — which writes
    // the Windows stock value, a different promise than "put it back".
    render(<TweakListRow setting={makeSetting({ originalValue: undefined })} />);

    expect(undoButton()).not.toBeInTheDocument();
  });

  it("stays hidden when the value is already what it was", () => {
    render(<TweakListRow setting={makeSetting({ originalValue: 5, currentValue: 5 })} />);

    expect(undoButton()).not.toBeInTheDocument();
  });

  it("treats a recorded null as nothing recorded", () => {
    // The API returns null for a setting seen before the originals store
    // existed, and `null !== undefined` is exactly the kind of difference that
    // renders a button which then cannot do anything.
    render(<TweakListRow setting={makeSetting({ originalValue: null })} />);

    expect(undoButton()).not.toBeInTheDocument();
  });
});

describe("apply is unaffected by any of this", () => {
  it("still applies the recommended value", async () => {
    const setting = makeSetting({ isOptimized: false, currentValue: 100 });
    render(<TweakListRow setting={setting} />);

    await userEvent.click(screen.getByRole("button", { name: /^Apply / }));

    expect(applySingle).toHaveBeenCalledWith(setting, 5);
  });
});
