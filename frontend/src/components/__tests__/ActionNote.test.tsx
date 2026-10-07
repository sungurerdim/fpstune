/**
 * What a cleanup row says on its one line, and the one number it must never invent.
 *
 * Ported from the card this replaces (`ActionRow`), which spread the same account
 * over a block per action: what it can reclaim, what it is doing right now, what
 * it did. Here it is one line beside the name, and every claim keeps the rule it
 * had: a size is shown only once measured, a percentage only if the command
 * printed one, a freed figure only from the backend's own before-and-after pair.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ActionNote } from "../ActionNote";
import { useStore, type RunStep } from "../../store";
import type { Setting } from "../../types/setting";

function cleanupSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "cleanup:temp_files" as `${string}:${string}`,
    domain: "software",
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

function result(freedMB: number | null, sized = freedMB !== null) {
  return {
    "cleanup:temp_files": {
      id: "cleanup:temp_files",
      name: "Temp Files",
      success: true,
      sized,
      freedMB,
    },
  };
}

beforeEach(() => {
  useStore.setState({ cleanupResults: {}, runSteps: [] });
});

describe("what the row says before it is run", () => {
  it("shows the measured size the scan reported", () => {
    render(<ActionNote setting={cleanupSetting({ currentValue: "ready|4096 MB" })} />);

    expect(screen.getByText("4096 MB")).toBeInTheDocument();
  });

  it("says a size is still being measured rather than showing a number", () => {
    render(<ActionNote setting={cleanupSetting({ currentValue: "ready|calculating" })} />);

    expect(screen.getByText("Calculating…")).toBeInTheDocument();
    expect(screen.queryByText(/MB/)).not.toBeInTheDocument();
  });

  it("says so when the service that would measure it is down", () => {
    render(<ActionNote setting={cleanupSetting({ currentValue: "ready|unavailable" })} />);

    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("shows nothing at all for an action that reclaims nothing", () => {
    // A repair has no reclaimable size, and a "0 MB" badge would read as one
    // that had been measured (C11).
    const { container } = render(
      <ActionNote setting={cleanupSetting({ module: "maintenance", currentValue: null })} />,
    );

    expect(screen.queryByText(/MB/)).not.toBeInTheDocument();
    expect(container).toHaveTextContent("");
  });
});

describe("what the row says while it runs", () => {
  it("shows the percentage the command printed", () => {
    useStore.setState({ runSteps: [step({ percent: 42, reportsProgress: true })] });

    render(<ActionNote setting={cleanupSetting()} />);

    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("shows elapsed seconds, not a percentage, for a command that prints none (C11)", () => {
    // A folder delete prints no progress. Elapsed time is shown instead of a
    // number nothing measured.
    useStore.setState({ runSteps: [step({ percent: null, startedAt: Date.now() - 7000 })] });

    render(<ActionNote setting={cleanupSetting()} />);

    expect(screen.getByText(/\d+s elapsed/)).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("keeps the command verbatim and its newest line on hover", () => {
    // Not a paraphrase: this is the record of what fpstune ran on the machine.
    useStore.setState({
      runSteps: [step({ lines: ["The operation is 42% complete"] })],
    });

    render(<ActionNote setting={cleanupSetting()} />);

    const progress = screen.getByText(/\d+s elapsed/);
    expect(progress.getAttribute("title")).toBe(
      "Dism.exe /online /Cleanup-Image /RestoreHealth\nThe operation is 42% complete",
    );
  });

  it("shows nothing of another action's run", () => {
    useStore.setState({ runSteps: [step({ id: "cleanup:prefetch", name: "Prefetch Files" })] });

    render(<ActionNote setting={cleanupSetting()} />);

    expect(screen.queryByText(/elapsed/)).not.toBeInTheDocument();
  });
});

describe("what the row says once it has run", () => {
  it("reports the space the backend measured this run freeing", () => {
    useStore.setState({
      runSteps: [step({ status: "done", endedAt: Date.now() })],
      cleanupResults: result(2048),
    });

    render(<ActionNote setting={cleanupSetting()} />);

    expect(screen.getByText("Freed 2.0 GB")).toBeInTheDocument();
    expect(screen.queryByText(/elapsed/)).not.toBeInTheDocument();
  });

  it("says only 'Done' when nothing measured a byte count (C11 rule 3)", () => {
    // A repair frees nothing, and a cleanup whose new size never came back has
    // no difference to report. Neither becomes a zero.
    useStore.setState({ cleanupResults: result(null) });

    render(<ActionNote setting={cleanupSetting()} />);

    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.queryByText(/Freed/)).not.toBeInTheDocument();
  });

  it("leaves a failure to the row's own status mark", () => {
    // The mark carries the reason; a second statement of it here would be the
    // same outcome reported twice on one line.
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

    render(<ActionNote setting={cleanupSetting()} />);

    expect(screen.queryByText(/Failed|denied|Done|Freed/)).not.toBeInTheDocument();
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
  const retrim = (currentValue: string) =>
    cleanupSetting({
      id: "maintenance:ssd_retrim" as `${string}:${string}`,
      module: "maintenance",
      name: "ssd_retrim",
      displayName: "SSD TRIM Overdue",
      currentValue,
    });

  it("warns that a retrim has never run, and shows no size", () => {
    render(<ActionNote setting={retrim("overdue|never")} />);

    expect(screen.getByText("TRIM overdue: never run")).toBeInTheDocument();
    expect(screen.queryByText("never")).not.toBeInTheDocument();
    expect(screen.queryByText(/MB|GB/)).not.toBeInTheDocument();
  });

  it("says how long the retrim has been overdue, as a duration not a size", () => {
    render(<ActionNote setting={retrim("overdue|23 days")} />);

    expect(screen.getByText("TRIM overdue: 23 days ago")).toBeInTheDocument();
    // The defect verbatim: "23 days" in the badge the sizes use.
    expect(screen.queryByText("23 days")).not.toBeInTheDocument();
  });

  it("states the last retrim quietly when nothing is overdue", () => {
    render(<ActionNote setting={retrim("ok|3 days")} />);

    expect(screen.getByText("Last TRIM: 3 days ago")).toBeInTheDocument();
    expect(screen.queryByText(/TRIM overdue/)).not.toBeInTheDocument();
  });

  it("turns over on the reading the run itself reported", () => {
    const { rerender } = render(<ActionNote setting={retrim("overdue|23 days")} />);
    expect(screen.getByText("TRIM overdue: 23 days ago")).toBeInTheDocument();

    rerender(<ActionNote setting={retrim("ok|0 days")} />);

    expect(screen.queryByText(/TRIM overdue/)).not.toBeInTheDocument();
    expect(screen.getByText("Last TRIM: less than a day ago")).toBeInTheDocument();
  });

  it("shows no badge for a reading it could not account for", () => {
    // Never a guess: "never run" is a claim about this machine (C11 rule 3).
    render(<ActionNote setting={retrim("overdue|soon")} />);

    expect(screen.queryByText(/TRIM overdue/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Last TRIM/)).not.toBeInTheDocument();
    expect(screen.queryByText("soon")).not.toBeInTheDocument();
  });
});
