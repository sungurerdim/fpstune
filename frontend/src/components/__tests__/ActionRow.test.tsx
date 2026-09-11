/**
 * An action has exactly one place on screen, and everything it can say says it
 * there.
 *
 * Pressing Run used to open a separate "running" panel that listed a *copy* of
 * every selected action while the originals stayed in the list below. A single
 * cleanup was on the page twice — its reclaimable size in one row, its progress
 * in another — and the user had to match them by name. These tests hold the
 * whole account in one card: what it can reclaim, what it is doing right now,
 * what it did, and the one number it must never invent.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ActionRow } from "../ActionRow";
import { makeRunner } from "../../test/runner";
import { useStore, type RunStep } from "../../store";
import type { Setting } from "../../types/setting";

function cleanupSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "cleanup:temp_files" as `${string}:${string}`,
    module: "cleanup",
    name: "temp_files",
    displayName: "Temp Files",
    description: "Clears temporary files from the system.",
    category: "cleanup",
    valueType: "bool",
    choices: [],
    defaultValue: false,
    recommendedValue: true,
    requiresReboot: false,
    isAction: true,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    categoryOrder: 0,
    riskLevel: "safe",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "ready|4096 MB",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
    ...overrides,
  };
}

function step(overrides: Partial<RunStep> = {}): RunStep {
  return {
    id: "cleanup:temp_files",
    name: "Temp Files",
    status: "running",
    command: "Dism.exe /online /Cleanup-Image /RestoreHealth",
    percent: null,
    reportsProgress: false,
    durationEstimate: "",
    lines: [],
    startedAt: Date.now(),
    endedAt: null,
    ...overrides,
  };
}

beforeEach(() => {
  useStore.setState({
    cleanupResults: {},
    runSteps: [],
    maintenanceSelection: {},
  });
});

describe("what the row says before it is run", () => {
  it("leads with the name and what the action does", () => {
    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(screen.getByText("Temp Files")).toBeInTheDocument();
    expect(
      screen.getByText("Clears temporary files from the system."),
    ).toBeInTheDocument();
  });

  it("shows the measured size the scan reported", () => {
    render(
      <ActionRow
        setting={cleanupSetting({ currentValue: "ready|4096 MB" })}
        runner={makeRunner()}
      />,
    );

    expect(screen.getByText("4096 MB")).toBeInTheDocument();
  });

  it("says a size is still being measured rather than showing a number", () => {
    render(
      <ActionRow
        setting={cleanupSetting({ currentValue: "ready|calculating" })}
        runner={makeRunner()}
      />,
    );

    expect(screen.getByText("Calculating…")).toBeInTheDocument();
    expect(screen.queryByText(/MB/)).not.toBeInTheDocument();
  });

  it("says so when the service that would measure it is down", () => {
    render(
      <ActionRow
        setting={cleanupSetting({ currentValue: "ready|unavailable" })}
        runner={makeRunner()}
      />,
    );

    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("shows no size badge at all for an action that reclaims nothing", () => {
    // A repair has no reclaimable size, and a "0 MB" badge would read as one
    // that had been measured (C11).
    render(
      <ActionRow
        setting={cleanupSetting({
          id: "maintenance:sfc_scan" as `${string}:${string}`,
          module: "maintenance",
          name: "sfc_scan",
          displayName: "SFC Scan",
          currentValue: null,
        })}
        runner={makeRunner()}
        accent="warning"
      />,
    );

    expect(screen.queryByText("Calculating…")).not.toBeInTheDocument();
    expect(screen.queryByText(/MB/)).not.toBeInTheDocument();
  });

  it("shows how long the backend says the action takes", () => {
    render(
      <ActionRow
        setting={cleanupSetting({ durationEstimate: "5-15 min" })}
        runner={makeRunner()}
      />,
    );

    expect(screen.getByText("(5-15 min)")).toBeInTheDocument();
  });

  it("warns that a docker prune restarts Docker and WSL before it is pressed", () => {
    render(
      <ActionRow
        setting={cleanupSetting({
          id: "cleanup:docker_prune" as `${string}:${string}`,
          name: "docker_prune",
          displayName: "Docker Prune",
        })}
        runner={makeRunner()}
      />,
    );

    expect(screen.getByText(/Docker Desktop/)).toBeInTheDocument();
    expect(screen.getByText(/WSL distributions/)).toBeInTheDocument();
  });

  it("carries the repair's own precondition", () => {
    render(
      <ActionRow
        setting={cleanupSetting({
          id: "maintenance:dism_health" as `${string}:${string}`,
          module: "maintenance",
          name: "dism_health",
          displayName: "DISM Health Check",
          currentValue: null,
        })}
        runner={makeRunner()}
        accent="warning"
      />,
    );

    expect(
      screen.getByText(/May require internet connection/),
    ).toBeInTheDocument();
  });

  it("states a cleanup's effect but never restates a repair's description", () => {
    // For SFC and DISM "what it does" and "what running it does" are the same
    // sentence, so an effect line printed the description a second time.
    const effect = "Frees space taken by temporary files";
    const { unmount } = render(
      <ActionRow setting={cleanupSetting({ effect })} runner={makeRunner()} />,
    );
    expect(screen.getByText(effect)).toBeInTheDocument();
    unmount();

    render(
      <ActionRow
        setting={cleanupSetting({
          id: "maintenance:sfc_scan" as `${string}:${string}`,
          module: "maintenance",
          name: "sfc_scan",
          displayName: "SFC Scan",
          currentValue: null,
          effect,
        })}
        runner={makeRunner()}
        accent="warning"
      />,
    );
    expect(screen.queryByText(effect)).not.toBeInTheDocument();
  });
});

describe("running the action from its own row", () => {
  it("runs this action and no other", async () => {
    const run = vi.fn();
    render(
      <ActionRow setting={cleanupSetting()} runner={makeRunner({ run })} />,
    );

    await userEvent.click(screen.getByRole("button", { name: /run/i }));

    expect(run).toHaveBeenCalledWith(["cleanup:temp_files"]);
  });

  it("cannot be pressed twice while the runner is busy", () => {
    render(
      <ActionRow
        setting={cleanupSetting()}
        runner={makeRunner({ isRunning: true })}
      />,
    );

    expect(screen.getByRole("button", { name: /run/i })).toBeDisabled();
  });

  it("offers the shared bulk-selection checkbox only where one belongs", () => {
    const { unmount } = render(
      <ActionRow setting={cleanupSetting()} runner={makeRunner()} selectable />,
    );
    expect(screen.getByRole("checkbox", { name: "Temp Files" })).toBeInTheDocument();
    unmount();

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("selects the action for the bulk Run when the box is ticked", async () => {
    render(
      <ActionRow setting={cleanupSetting()} runner={makeRunner()} selectable />,
    );

    await userEvent.click(screen.getByRole("checkbox", { name: "Temp Files" }));

    expect(useStore.getState().maintenanceSelection).toEqual({
      "cleanup:temp_files": true,
    });
  });
});

describe("what the row says while it runs — in the row, not beside it", () => {
  it("shows the command that is actually running, verbatim", () => {
    // Not a paraphrase: this is the record of what fpstune ran on the machine.
    useStore.setState({ runSteps: [step()] });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(
      screen.getByText("Dism.exe /online /Cleanup-Image /RestoreHealth"),
    ).toBeInTheDocument();
  });

  it("draws a bar from the percentage the command printed", () => {
    useStore.setState({
      runSteps: [step({ percent: 42, reportsProgress: true })],
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    const bar = screen.getByRole("progressbar", { name: /Temp Files/ });
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("draws no bar for a command that reports no percentage (C11)", () => {
    // A folder delete prints no progress. Elapsed time is shown instead of a
    // number nothing measured.
    useStore.setState({
      runSteps: [step({ percent: null, startedAt: Date.now() - 7000 })],
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText(/\d+s elapsed/)).toBeInTheDocument();
  });

  it("shows the latest output line as the current stage", () => {
    useStore.setState({
      runSteps: [
        step({
          lines: ["Version: 10.0.26200.1", "The operation is 42% complete"],
        }),
      ],
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(
      screen.getByText("The operation is 42% complete"),
    ).toBeInTheDocument();
    // The earlier lines are the log, not the headline: they are behind a toggle.
    expect(screen.queryByText("Version: 10.0.26200.1")).not.toBeInTheDocument();
  });

  it("keeps the whole output one keystroke away", async () => {
    useStore.setState({
      runSteps: [step({ lines: ["Version: 10.0.26200.1", "Working"] })],
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);
    await userEvent.click(screen.getByRole("button", { expanded: false }));

    expect(screen.getByText(/Version: 10\.0\.26200\.1/)).toBeInTheDocument();
  });

  it("names the failure on the row that failed", () => {
    useStore.setState({
      runSteps: [
        step({
          status: "failed",
          error: "PowerShell command timed out after 300s",
        }),
      ],
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(
      screen.getByText("PowerShell command timed out after 300s"),
    ).toBeInTheDocument();
  });

  it("says an action was queued, and that another was not applicable", () => {
    useStore.setState({ runSteps: [step({ status: "queued" })] });
    const { unmount } = render(
      <ActionRow setting={cleanupSetting()} runner={makeRunner()} />,
    );
    expect(screen.getByText("queued")).toBeInTheDocument();
    unmount();

    useStore.setState({ runSteps: [step({ status: "skipped" })] });
    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);
    expect(screen.getByText("Not applicable")).toBeInTheDocument();
  });

  it("shows nothing of another action's run", () => {
    useStore.setState({
      runSteps: [step({ id: "cleanup:prefetch", name: "Prefetch Files" })],
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Dism.exe /online /Cleanup-Image /RestoreHealth"),
    ).not.toBeInTheDocument();
  });
});

describe("what the row says once it has run — in the row, not beside it", () => {
  it("reports the space the backend measured this run freeing", () => {
    useStore.setState({
      runSteps: [step({ status: "done", endedAt: Date.now() })],
      cleanupResults: {
        "cleanup:temp_files": {
          id: "cleanup:temp_files",
          name: "Temp Files",
          success: true,
          sized: true,
          freedMB: 2048,
        },
      },
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(screen.getByText("Freed 2.0 GB")).toBeInTheDocument();
  });

  it("says only 'Done' when nothing measured a byte count (C11 rule 3)", () => {
    // A repair frees nothing, and a cleanup whose new size never came back has
    // no difference to report. Neither becomes a zero.
    useStore.setState({
      cleanupResults: {
        "cleanup:temp_files": {
          id: "cleanup:temp_files",
          name: "Temp Files",
          success: true,
          sized: false,
          freedMB: null,
        },
      },
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.queryByText(/Freed/)).not.toBeInTheDocument();
  });

  it("reports a failure with the reason, in place", () => {
    useStore.setState({
      cleanupResults: {
        "cleanup:temp_files": {
          id: "cleanup:temp_files",
          name: "Temp Files",
          success: false,
          sized: false,
          freedMB: null,
          error: "Access to the path is denied",
        },
      },
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(
      screen.getByText(/Failed: Access to the path is denied/),
    ).toBeInTheDocument();
  });

  it("states the outcome exactly once — never beside a leftover step line", () => {
    // The defect this card replaces: the same finished action reported in two
    // places at once. Once a run has an outcome, the finished step's own line
    // has nothing left to add.
    useStore.setState({
      runSteps: [step({ status: "done", endedAt: Date.now() })],
      cleanupResults: {
        "cleanup:temp_files": {
          id: "cleanup:temp_files",
          name: "Temp Files",
          success: true,
          sized: true,
          freedMB: 2048,
        },
      },
    });

    render(<ActionRow setting={cleanupSetting()} runner={makeRunner()} />);

    expect(screen.getAllByText("Temp Files")).toHaveLength(1);
    expect(screen.getAllByText("Freed 2.0 GB")).toHaveLength(1);
    expect(screen.queryByText("Done")).not.toBeInTheDocument();
  });
});

/**
 * A reading is rendered as the kind of thing it is.
 *
 * `maintenance:ssd_retrim` reports `overdue|never`, `overdue|23 days` or
 * `ok|3 days`, and every action reading used to go through the size parser —
 * which splits on "|" and shows whatever follows. So a machine whose SSDs had
 * never been retrimmed displayed "never" in a badge with a hard-drive icon,
 * beside cleanups measured in megabytes: a maintenance date presented as an
 * amount of reclaimable disk space.
 */
describe("what the row says about a maintenance reading", () => {
  function retrim(currentValue: string): Setting {
    return cleanupSetting({
      id: "maintenance:ssd_retrim" as `${string}:${string}`,
      module: "maintenance",
      name: "ssd_retrim",
      displayName: "SSD TRIM Overdue",
      currentValue,
    });
  }

  it("warns that a retrim has never run, and shows no size", () => {
    render(<ActionRow setting={retrim("overdue|never")} runner={makeRunner()} />);

    expect(screen.getByText("TRIM overdue: never run")).toBeInTheDocument();
    expect(screen.queryByText("never")).not.toBeInTheDocument();
    expect(screen.queryByText(/MB|GB/)).not.toBeInTheDocument();
  });

  it("says how long the retrim has been overdue, as a duration not a size", () => {
    render(
      <ActionRow setting={retrim("overdue|23 days")} runner={makeRunner()} />,
    );

    expect(screen.getByText("TRIM overdue: 23 days ago")).toBeInTheDocument();
    // The defect verbatim: "23 days" in the badge the sizes use.
    expect(screen.queryByText("23 days")).not.toBeInTheDocument();
  });

  it("states the last retrim quietly when nothing is overdue", () => {
    render(<ActionRow setting={retrim("ok|3 days")} runner={makeRunner()} />);

    expect(screen.getByText("Last TRIM: 3 days ago")).toBeInTheDocument();
    expect(screen.queryByText(/TRIM overdue/)).not.toBeInTheDocument();
  });

  it("reads the state the run itself reported, the moment it lands", () => {
    // The `applied` event carries `ok|0 days`, which the runner writes into the
    // store — so the badge the user is looking at turns over on the same tick.
    const { rerender } = render(
      <ActionRow setting={retrim("overdue|23 days")} runner={makeRunner()} />,
    );
    expect(screen.getByText("TRIM overdue: 23 days ago")).toBeInTheDocument();

    rerender(<ActionRow setting={retrim("ok|0 days")} runner={makeRunner()} />);

    expect(screen.queryByText(/TRIM overdue/)).not.toBeInTheDocument();
    expect(
      screen.getByText("Last TRIM: less than a day ago"),
    ).toBeInTheDocument();
  });

  it("shows no badge for a reading it could not account for", () => {
    // Never a guess: "never run" is a claim about this machine (C11 rule 3).
    render(<ActionRow setting={retrim("overdue|soon")} runner={makeRunner()} />);

    expect(screen.queryByText(/TRIM overdue/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Last TRIM/)).not.toBeInTheDocument();
    expect(screen.queryByText("soon")).not.toBeInTheDocument();
  });
});
