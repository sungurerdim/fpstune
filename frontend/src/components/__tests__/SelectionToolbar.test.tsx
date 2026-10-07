/**
 * The advanced-tweaks gate, at the place it actually stands.
 *
 * `ConfirmDialog` being correct is not the same as this toolbar using it
 * correctly: the failure that shipped was a confirmation the keyboard could walk
 * away from, and the thing that must never happen is a bulk apply of settings
 * marked Advanced running because the question was skipped rather than answered.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "../../test/utils";
import { SelectionToolbar } from "../SelectionToolbar";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const bulkStreamApply = vi.fn((_settings: Record<string, unknown>) => () => {});
const restorePoint = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, createRestorePoint: () => restorePoint() },
    settingsApi: {
      ...actual.settingsApi,
      // Only the {id: value} map matters here; the SSE callbacks are the
      // stream's business and are exercised where the stream is.
      bulkStreamApply: (settings: Record<string, unknown>) =>
        bulkStreamApply(settings),
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

function makeScoped(id: string, scope: Setting["scope"], over: Partial<Setting> = {}): Setting {
  return { ...makeSetting(id, "low"), scope, ...over } as Setting;
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
  });

  it("asks as a real dialog before applying anything marked Advanced", () => {
    select(makeSetting("system:experimental", "advanced"));
    render(<SelectionToolbar />);

    fireEvent.click(screen.getByRole("button", { name: /^Apply selected \(1\)/ }));

    expect(
      screen.getByRole("dialog", { name: "Advanced tweaks selected" }),
    ).toHaveAttribute("aria-modal", "true");
    expect(bulkStreamApply).not.toHaveBeenCalled();
  });

  it("does not apply when the dialog is dismissed from the keyboard", () => {
    select(makeSetting("system:experimental", "advanced"));
    render(<SelectionToolbar />);

    fireEvent.click(screen.getByRole("button", { name: /^Apply selected \(1\)/ }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(bulkStreamApply).not.toHaveBeenCalled();
  });

  it("applies once the question is actually answered", () => {
    select(makeSetting("system:experimental", "advanced"));
    render(<SelectionToolbar />);

    fireEvent.click(screen.getByRole("button", { name: /^Apply selected \(1\)/ }));
    fireEvent.click(screen.getByRole("button", { name: "Apply anyway" }));

    expect(bulkStreamApply).toHaveBeenCalledTimes(1);
    // Apply writes the recommendation: one stream request, {id: recommended}.
    expect(bulkStreamApply.mock.calls[0][0]).toEqual({
      "system:experimental": "disabled",
    });
  });

  it("asks with the count when no selected tweak is Advanced, like every scope", () => {
    select(makeSetting("system:ordinary", "low"));
    render(<SelectionToolbar />);

    fireEvent.click(screen.getByRole("button", { name: /^Apply selected \(1\)/ }));
    expect(screen.getByRole("dialog", { name: "Apply 1 tweaks on 1 selected?" })).toBeTruthy();
    expect(bulkStreamApply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(bulkStreamApply).toHaveBeenCalledTimes(1);
  });

  it("offers one Reset to default for a selection, names the Windows default, and resets after asking", () => {
    select({ ...makeSetting("system:ordinary", "low"), currentValue: "disabled" } as Setting);
    render(<SelectionToolbar />);

    // No overflow menu and no second way back: one button, named by the domain.
    expect(screen.queryByRole("button", { name: /^More actions/ })).toBeNull();
    const resetButton = screen.getByRole("button", { name: "Reset selected to default (1)" });
    expect(resetButton).toHaveAttribute(
      "title",
      "Reset 1 settings to the Windows default: 1 selected",
    );
    fireEvent.click(resetButton);
    expect(bulkStreamApply).not.toHaveBeenCalled();

    // Reset is the same stream with each row's own default as its value.
    fireEvent.click(screen.getByRole("button", { name: "Reset to default" }));
    expect(bulkStreamApply).toHaveBeenCalledTimes(1);
    expect(bulkStreamApply.mock.calls[0][0]).toEqual({
      "system:ordinary": "enabled",
    });
  });

  it("disables Reset to default, saying why, when the selection is already at its defaults", () => {
    select(makeSetting("system:ordinary", "low"));
    render(<SelectionToolbar />);

    const resetButton = screen.getByRole("button", { name: "Reset selected to default (0)" });
    expect(resetButton).toBeDisabled();
    expect(resetButton).toHaveAttribute("title", "Everything in 1 selected is already at its default");
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

    expect(screen.queryByRole("button", { name: /^Apply selected \(1\)/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Stop/ })).toBeTruthy();
  });
});


describe("SelectionToolbar's scope buttons", () => {
  const rows = [
    makeScoped("system:essential_row", "essential"),
    makeScoped("system:recommended_row", "recommended"),
    makeScoped("system:complete_row", "complete"),
    // Not written: already optimized, and an advisory fpstune cannot write.
    makeScoped("system:already_row", "essential", { status: "optimal", isOptimized: true }),
    makeScoped("system:advisory_row", "essential", { isReadonly: true }),
  ];

  beforeEach(() => {
    bulkStreamApply.mockClear();
    restorePoint.mockReset().mockResolvedValue({ success: true, message: "" });
    useStore.setState({
      settings: new Map(rows.map((s) => [s.id, s])),
      selectedSettingIds: new Set(),
      operationStatus: {},
      operationError: {},
      bulkRun: null,
    } as never);
  });

  it("is hidden without a selection or a scope", () => {
    const { container } = render(<SelectionToolbar />);
    expect(container).toBeEmptyDOMElement();
  });

  it("counts each level over the not-optimized, writable rows only", () => {
    render(<SelectionToolbar settings={rows} name="Software" />);

    expect(screen.getByRole("button", { name: "Apply essential (1)" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Apply recommended (2)" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Apply complete (3)" })).toBeEnabled();
  });

  it("Apply recommended asks, then sends one stream request with essential + recommended, never complete", async () => {
    render(<SelectionToolbar settings={rows} name="Software" />);

    fireEvent.click(screen.getByRole("button", { name: "Apply recommended (2)" }));
    expect(screen.getByRole("dialog", { name: "Apply 2 tweaks on Software?" })).toBeTruthy();
    expect(bulkStreamApply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(bulkStreamApply).toHaveBeenCalledTimes(1));
    expect(bulkStreamApply.mock.calls[0][0]).toEqual({
      "system:essential_row": "disabled",
      "system:recommended_row": "disabled",
    });
  });

  it("makes Apply recommended the primary button", () => {
    render(<SelectionToolbar settings={rows} name="Software" />);

    expect(screen.getByRole("button", { name: "Apply recommended (2)" }).className).toMatch(
      /bg-primary/,
    );
    expect(screen.getByRole("button", { name: "Apply essential (1)" }).className).not.toMatch(
      /bg-primary/,
    );
  });

  it("disables a level with nothing to write, saying why", () => {
    render(<SelectionToolbar settings={[rows[3], rows[4]]} name="Software" />);

    const button = screen.getByRole("button", { name: "Apply essential (0)" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Nothing to apply in Software");
  });

  it("asks the advanced question for a level that includes an Advanced row", () => {
    const advanced = makeScoped("system:risky_row", "complete", { riskLevel: "advanced" });
    render(<SelectionToolbar settings={[advanced]} name="Software" />);

    fireEvent.click(screen.getByRole("button", { name: "Apply complete (1)" }));
    expect(screen.getByRole("dialog", { name: "Advanced tweaks selected" })).toBeTruthy();
    expect(bulkStreamApply).not.toHaveBeenCalled();
  });
});


describe("a page-wide apply asks for a restore point, and says what it costs", () => {
  const costly = makeScoped("game_config:mw4:model_quality", "complete", {
    perceptibleCost:
      "Characters and objects render at reduced model detail; at long range, identification takes a beat longer.",
  });
  const rows = [makeScoped("system:essential_row", "essential"), makeScoped("system:recommended_row", "recommended"), costly];

  beforeEach(() => {
    bulkStreamApply.mockClear();
    restorePoint.mockReset().mockResolvedValue({ success: true, message: "" });
    useStore.setState({
      settings: new Map(rows.map((s) => [s.id, s])),
      selectedSettingIds: new Set(),
      operationStatus: {},
      operationError: {},
      notifications: [],
      bulkRun: null,
    } as never);
  });

  it("creates the restore point before the apply when asked", async () => {
    render(<SelectionToolbar settings={rows} name="Software" />);

    fireEvent.click(screen.getByRole("button", { name: "Apply recommended (2)" }));
    expect(screen.getByRole("checkbox", { name: /System Restore point/ })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(bulkStreamApply).toHaveBeenCalledTimes(1));
    expect(restorePoint).toHaveBeenCalledTimes(1);
    expect(restorePoint.mock.invocationCallOrder[0]).toBeLessThan(
      bulkStreamApply.mock.invocationCallOrder[0],
    );
  });

  it("skips it when the box is cleared", async () => {
    render(<SelectionToolbar settings={rows} name="Software" />);

    fireEvent.click(screen.getByRole("button", { name: "Apply recommended (2)" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /System Restore point/ }));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(bulkStreamApply).toHaveBeenCalledTimes(1));
    expect(restorePoint).not.toHaveBeenCalled();
  });

  it("applies nothing, and says so, when the restore point could not be made", async () => {
    // The user asked for the safety net; going ahead without it would honour
    // the button and betray the checkbox.
    restorePoint.mockResolvedValue({ success: false, message: "System Protection is off" });
    render(<SelectionToolbar settings={rows} name="Software" />);

    fireEvent.click(screen.getByRole("button", { name: "Apply recommended (2)" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() =>
      expect(useStore.getState().notifications.map((n) => n.message).join(" ")).toMatch(
        /Restore point failed — nothing was applied\. System Protection is off/,
      ),
    );
    expect(bulkStreamApply).not.toHaveBeenCalled();
  });

  it("lists what a row spends before anything runs, and applies nothing if cancelled", () => {
    render(<SelectionToolbar settings={rows} name="Software" />);

    fireEvent.click(screen.getByRole("button", { name: "Apply complete (3)" }));

    // The cost copy is on screen before anything runs (consequence 5).
    expect(screen.getByText(/reduced model detail/)).toBeInTheDocument();
    expect(screen.getByText(/What you give up/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(bulkStreamApply).not.toHaveBeenCalled();
    expect(restorePoint).not.toHaveBeenCalled();
  });

  it("says nothing about costs when no row spends anything", () => {
    render(<SelectionToolbar settings={rows} name="Software" />);

    fireEvent.click(screen.getByRole("button", { name: "Apply recommended (2)" }));

    expect(screen.queryByText(/What you give up/)).not.toBeInTheDocument();
  });

  it("offers a ticked selection no restore point: it is not a page-wide write", () => {
    select(makeSetting("system:ordinary", "low"));
    render(<SelectionToolbar />);

    fireEvent.click(screen.getByRole("button", { name: /^Apply selected \(1\)/ }));

    expect(screen.queryByRole("checkbox", { name: /System Restore point/ })).not.toBeInTheDocument();
  });
});
