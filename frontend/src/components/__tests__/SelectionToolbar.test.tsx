/**
 * The advanced-tweaks gate, at the place it actually stands.
 *
 * `ConfirmDialog` being correct is not the same as this toolbar using it
 * correctly: the failure that shipped was a confirmation the keyboard could walk
 * away from, and the thing that must never happen is a bulk apply of settings
 * marked Advanced running because the question was skipped rather than answered.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "../../test/utils";
import { SelectionToolbar } from "../SelectionToolbar";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const bulkStreamApply = vi.fn((_ids: string[]) => () => {});
const bulkStreamReset = vi.fn((_ids: string[]) => () => {});

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    settingsApi: {
      ...actual.settingsApi,
      // Only the ids matter here; the SSE callbacks are the stream's business
      // and are exercised where the stream is.
      bulkStreamApply: (ids: string[]) => bulkStreamApply(ids),
      bulkStreamReset: (ids: string[]) => bulkStreamReset(ids),
    },
  };
});

function makeSetting(id: string, riskLevel: Setting["riskLevel"]): Setting {
  return {
    id: id as `${string}:${string}`,
    domain: "software",
    module: id.split(":")[0],
    name: id.split(":").slice(1).join(":"),
    displayName: "A Tweak",
    description: "Controls something. It matters for latency.",
    impactCategories: [],
    category: "network",
    valueType: "choice",
    choices: ["enabled", "disabled"],
    defaultValue: "enabled",
    recommendedValue: "disabled",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    categoryOrder: 0,
    riskLevel,
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "enabled",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
  } as Setting;
}

function select(setting: Setting) {
  useStore.setState({
    settings: new Map([[setting.id, setting]]),
    selectedSettingIds: new Set([setting.id]),
    operationStatus: {},
    operationError: {},
    bulkRun: null,
  } as never);
}

describe("SelectionToolbar's advanced gate", () => {
  beforeEach(() => {
    bulkStreamApply.mockClear();
    bulkStreamReset.mockClear();
  });

  it("asks as a real dialog before applying anything marked Advanced", () => {
    select(makeSetting("system:experimental", "advanced"));
    render(<SelectionToolbar />);

    fireEvent.click(screen.getByRole("button", { name: /^Apply 1 tweaks/ }));

    expect(
      screen.getByRole("dialog", { name: "Advanced tweaks selected" }),
    ).toHaveAttribute("aria-modal", "true");
    expect(bulkStreamApply).not.toHaveBeenCalled();
  });

  it("does not apply when the dialog is dismissed from the keyboard", () => {
    select(makeSetting("system:experimental", "advanced"));
    render(<SelectionToolbar />);

    fireEvent.click(screen.getByRole("button", { name: /^Apply 1 tweaks/ }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(bulkStreamApply).not.toHaveBeenCalled();
  });

  it("applies once the question is actually answered", () => {
    select(makeSetting("system:experimental", "advanced"));
    render(<SelectionToolbar />);

    fireEvent.click(screen.getByRole("button", { name: /^Apply 1 tweaks/ }));
    fireEvent.click(screen.getByRole("button", { name: "Apply anyway" }));

    expect(bulkStreamApply).toHaveBeenCalledTimes(1);
    expect(bulkStreamApply.mock.calls[0][0]).toEqual(["system:experimental"]);
  });

  it("asks with the count when no selected tweak is Advanced, like every scope", () => {
    select(makeSetting("system:ordinary", "low"));
    render(<SelectionToolbar />);

    fireEvent.click(screen.getByRole("button", { name: /^Apply 1 tweaks/ }));
    expect(screen.getByRole("dialog", { name: "Apply 1 tweaks on 1 selected?" })).toBeTruthy();
    expect(bulkStreamApply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(bulkStreamApply).toHaveBeenCalledTimes(1);
  });

  it("offers Undo for a selection only when a row has a recorded original", () => {
    select({ ...makeSetting("system:ordinary", "low"), originalValue: "disabled" } as Setting);
    render(<SelectionToolbar />);

    expect(screen.getByRole("button", { name: /^Undo 1 tweaks/ })).toBeTruthy();
  });
});


describe("SelectionToolbar's run", () => {
  beforeEach(() => {
    bulkStreamApply.mockClear();
  });

  it("does not start a second run while one is in flight elsewhere", () => {
    select(makeSetting("system:plain", "low"));
    useStore.setState({ bulkRun: { action: "apply", cancel: () => {} } } as never);
    render(<SelectionToolbar />);

    expect(screen.queryByRole("button", { name: /^Apply 1 tweaks/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Stop/ })).toBeTruthy();
  });
});
