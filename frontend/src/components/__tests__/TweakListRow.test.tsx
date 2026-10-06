/**
 * Home's compact row: apply from here, and take it back from here.
 *
 * A change made from Home must be reversible from Home — the one screen a new
 * user stays on. The way back is the same one every row has: Reset to default,
 * which writes the setting's own default (Windows', the driver's or the game's)
 * and names which. It appears when there is something to write and not
 * otherwise.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TweakListRow } from "../TweakListRow";
import type { Setting } from "../../types/setting";

const applySingle = vi.fn();
const resetSingle = vi.fn();

vi.mock("../../hooks/useApplySingle", () => ({
  useApplySingle: () => ({
    applySingle: (...args: unknown[]) => applySingle(...args),
    resetSingle: (...args: unknown[]) => resetSingle(...args),
    isPending: () => false,
  }),
}));

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "power:cpu_min_state" as `${string}:${string}`,
    domain: "software",
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
  resetSingle.mockClear();
});

const resetButton = () => screen.queryByRole("button", { name: /^Reset .* to default/i });

describe("the way back is on the screen you changed it from", () => {
  it("offers Reset to default once the value is away from the default", () => {
    render(<TweakListRow setting={makeSetting({ defaultValue: 100, currentValue: 5 })} />);

    expect(resetButton()).toBeInTheDocument();
    expect(resetButton()).toHaveTextContent("Reset to default");
  });

  it("says in the control's name which default it writes, and the value", () => {
    render(<TweakListRow setting={makeSetting({ defaultValue: 100, currentValue: 5 })} />);

    expect(resetButton()).toHaveAccessibleName(
      "Reset Minimum Processor State to default: Windows default (100)",
    );
  });

  it("names the driver default for a hardware setting", () => {
    render(
      <TweakListRow
        setting={makeSetting({ domain: "hardware", defaultValue: 100, currentValue: 5 })}
      />,
    );

    expect(resetButton()).toHaveAccessibleName(
      "Reset Minimum Processor State to default: Driver default (100)",
    );
  });

  it("resets the setting it is attached to", async () => {
    const setting = makeSetting({ defaultValue: 100, currentValue: 5 });
    render(<TweakListRow setting={setting} />);

    await userEvent.click(resetButton()!);

    expect(resetSingle).toHaveBeenCalledWith(setting);
    expect(applySingle).not.toHaveBeenCalled();
  });
});

describe("it never offers a reset that would write nothing", () => {
  it("stays hidden when the value already is the default", () => {
    render(<TweakListRow setting={makeSetting({ defaultValue: 5, currentValue: 5 })} />);

    expect(resetButton()).not.toBeInTheDocument();
  });

  it("stays hidden when the setting has no default of its own", () => {
    render(<TweakListRow setting={makeSetting({ defaultValue: null, currentValue: 5 })} />);

    expect(resetButton()).not.toBeInTheDocument();
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
