/**
 * Tests for CleanupListRow component.
 * Tests size badge rendering, result status, and Run button behavior.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CleanupListRow } from "../CleanupListRow";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";
import type { CleanupRunner } from "../../hooks/useCleanupRunner";

function makeCleanupSetting(overrides: Partial<Setting> = {}): Setting {
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

function makeRunner(overrides: Partial<CleanupRunner> = {}): CleanupRunner {
  return {
    selectedIds: [],
    selectedCount: 0,
    hasSelection: false,
    isRunning: false,
    run: vi.fn(),
    confirmIds: null,
    confirmRun: vi.fn(),
    cancelConfirm: vi.fn(),
    ...overrides,
  };
}

describe("CleanupListRow", () => {
  beforeEach(() => {
    useStore.setState({ cleanupResults: {} });
  });

  it("renders the setting display name", () => {
    const setting = makeCleanupSetting();
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(screen.getByText("Temp Files")).toBeInTheDocument();
  });

  it("renders the setting description", () => {
    const setting = makeCleanupSetting();
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(
      screen.getByText("Clears temporary files from the system."),
    ).toBeInTheDocument();
  });

  it("shows size badge for ready|N MB value", () => {
    const setting = makeCleanupSetting({ currentValue: "ready|4096 MB" });
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(screen.getByText("4096 MB")).toBeInTheDocument();
  });

  it("shows 'Calculating…' spinner for calculating size", () => {
    const setting = makeCleanupSetting({ currentValue: "ready|calculating" });
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(screen.getByText("Calculating…")).toBeInTheDocument();
  });

  it("shows 'Unavailable' badge for unavailable status", () => {
    const setting = makeCleanupSetting({ currentValue: "ready|unavailable" });
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("renders a Run button", () => {
    const setting = makeCleanupSetting();
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(screen.getByRole("button", { name: /run/i })).toBeInTheDocument();
  });

  it("calls runner.run with setting.id when Run is clicked", async () => {
    const user = userEvent.setup();
    const run = vi.fn();
    const setting = makeCleanupSetting();
    render(
      <CleanupListRow setting={setting} runner={makeRunner({ run })} />,
    );

    await user.click(screen.getByRole("button", { name: /run/i }));
    expect(run).toHaveBeenCalledWith(["cleanup:temp_files"]);
  });

  it("disables Run button when runner.isRunning=true", () => {
    const setting = makeCleanupSetting();
    render(
      <CleanupListRow
        setting={setting}
        runner={makeRunner({ isRunning: true })}
      />,
    );
    expect(screen.getByRole("button", { name: /run/i })).toBeDisabled();
  });

  it("shows 'Done' status when result.success=true and result.sized=false", () => {
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

    const setting = makeCleanupSetting();
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  it("shows freed space when result.success=true, result.sized=true, freedMB is set", () => {
    useStore.setState({
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

    const setting = makeCleanupSetting();
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    // fmtMB(2048) = "2.0 GB"
    expect(screen.getByText("Freed 2.0 GB")).toBeInTheDocument();
  });

  it("shows 'Failed' when result.success=false", () => {
    useStore.setState({
      cleanupResults: {
        "cleanup:temp_files": {
          id: "cleanup:temp_files",
          name: "Temp Files",
          success: false,
          sized: false,
          freedMB: null,
          error: "Access denied",
        },
      },
    });

    const setting = makeCleanupSetting();
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("shows docker warning for docker_prune settings", () => {
    const setting = makeCleanupSetting({
      id: "cleanup:docker_prune" as `${string}:${string}`,
      name: "docker_prune",
      displayName: "Docker Prune",
    });
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(
      screen.getByText(/Restarts Docker Desktop/i),
    ).toBeInTheDocument();
  });

  it("shows duration estimate when durationEstimate is provided", () => {
    const setting = makeCleanupSetting({ durationEstimate: "2-5 min" });
    render(<CleanupListRow setting={setting} runner={makeRunner()} />);
    expect(screen.getByText("(2-5 min)")).toBeInTheDocument();
  });
});
