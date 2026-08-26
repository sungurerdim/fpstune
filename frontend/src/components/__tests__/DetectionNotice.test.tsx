import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DetectionNotice } from "../DetectionNotice";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

/**
 * "Could not read" must never look like "not present".
 *
 * Every list filters `isApplicable === false` with a bare continue, and
 * detection *failures* used to vanish through the same filter — a machine
 * where half the detection failed looked identical to one that was already
 * optimal. The notice sits above the filter and keeps the two facts apart.
 */

function makeSetting(over: Partial<Setting> & Pick<Setting, "id">): Setting {
  return {
    module: over.id.split(":")[0],
    name: over.id.split(":").slice(1).join(":"),
    displayName: "A Tweak",
    description: "Controls something. It matters.",
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
    riskLevel: "low",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "enabled",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...over,
  } as Setting;
}

function seed(...settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
  } as never);
}

const FAILED = makeSetting({
  id: "network:receive_buffers" as `${string}:${string}`,
  displayName: "Receive Buffers",
  detectionError: "Detection timed out",
});

const ABSENT = makeSetting({
  id: "gpu-nvidia:reflex" as `${string}:${string}`,
  displayName: "NVIDIA Reflex",
  isApplicable: false,
  applicableReason: "Requires an NVIDIA GPU",
  currentValue: null,
});

const HEALTHY = makeSetting({
  id: "network:nagle" as `${string}:${string}`,
  displayName: "Nagle",
});

describe("DetectionNotice", () => {
  beforeEach(() => {
    useStore.setState({ settings: new Map() } as never);
  });

  it("says so when a detector failed, with the setting's own error", () => {
    seed(FAILED, HEALTHY);
    render(<DetectionNotice />);
    const toggle = screen.getByText(/1 setting could not be checked/);
    fireEvent.click(toggle);
    expect(screen.getByText(/Receive Buffers/)).toBeInTheDocument();
    expect(screen.getByText(/Detection timed out/)).toBeInTheDocument();
  });

  it("keeps a failure out of the doesn't-apply count, and vice versa", () => {
    seed(FAILED, ABSENT);
    render(<DetectionNotice />);
    expect(
      screen.getByText(/1 setting could not be checked/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText(/1 setting doesn't apply/));
    expect(screen.getByText(/Requires an NVIDIA GPU/)).toBeInTheDocument();
    // The failed row lives under the warning, never under "doesn't apply".
    expect(screen.queryByText(/NVIDIA Reflex — Detection timed out/)).toBeNull();
  });

  it("renders nothing on a machine where everything read clean", () => {
    seed(HEALTHY);
    const { container } = render(<DetectionNotice />);
    expect(container.firstChild).toBeNull();
  });

  it("reports only the settings its surface owns", () => {
    const gameFailed = makeSetting({
      id: "game_config:mw4:dxr" as `${string}:${string}`,
      displayName: "Ray Tracing",
      module: "game_config",
      detectionError: "config file locked",
    });
    seed(FAILED, gameFailed);
    render(<DetectionNotice owns={(s) => s.module === "game_config"} />);
    const toggle = screen.getByText(/1 setting could not be checked/);
    fireEvent.click(toggle);
    expect(screen.getByText(/Ray Tracing/)).toBeInTheDocument();
    expect(screen.queryByText(/Receive Buffers/)).toBeNull();
  });
});
