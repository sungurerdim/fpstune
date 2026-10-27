/**
 * An action (a cleanup, a repair) run through the one apply path.
 *
 * Ported from the cleanup runner this path replaced. The freed-space figure is
 * the product the Cleanup tab exists to show, and the frontend does not compute
 * it: it used to snapshot the size before a run, wait for the size poll to
 * notice a change, and subtract — which missed the change whenever the
 * re-measure landed first. Only the backend knows both readings belong to the
 * same run, so it takes them and reports the difference on `applied`.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useStore } from "../../store";
import { useApply } from "../useApply";
import { detectionManager } from "../../store/detection-manager";
import type { Setting } from "../../types/setting";

const { bulkStreamApply } = vi.hoisted(() => ({ bulkStreamApply: vi.fn() }));

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    settingsApi: {
      ...actual.settingsApi,
      bulkStreamApply: (...args: unknown[]) => bulkStreamApply(...args),
    },
  };
});

vi.mock("../../store/detection-manager", () => ({
  detectionManager: {
    redetectSettings: vi.fn().mockResolvedValue(undefined),
    detectCategory: vi.fn().mockResolvedValue(undefined),
    detectAll: vi.fn().mockResolvedValue(undefined),
    stopAll: vi.fn(),
    initializeStore: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: { refreshMonitors: vi.fn() },
}));

const MB = 1024 * 1024;

function action(
  id: string,
  module: string,
  name: string,
  overrides: Partial<Setting> = {},
): Setting {
  return {
    id: id as `${string}:${string}`,
    domain: "software",
    module,
    name,
    displayName: name.replace(/_/g, " "),
    description: "Cleanup action.",
    category: "cleanup",
    valueType: "bool",
    choices: [],
    defaultValue: false,
    recommendedValue: false,
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
    currentValue: "ready|500 MB",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
    ...overrides,
  };
}

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

type Emit = (event: Record<string, unknown>) => void;

/** Start a run of `ids` and hand back the function that feeds it stream events. */
function startRun(ids: string[]): { emit: Emit; sent: () => unknown } {
  let onEvent: Emit = () => undefined;
  bulkStreamApply.mockImplementation((_targets: unknown, handler: Emit) => {
    onEvent = handler;
    return () => undefined;
  });
  const { result } = renderHook(() => useApply(), { wrapper: wrapper() });
  act(() => result.current.run("apply", ids));
  return {
    emit: (event) => act(() => onEvent(event)),
    sent: () => bulkStreamApply.mock.calls[bulkStreamApply.mock.calls.length - 1]?.[0],
  };
}

const started = (id: string) => ({
  event: "started",
  id,
  name: "Temp Files",
  duration_estimate: "",
  reports_progress: false,
});

const applied = (id: string, extra: Record<string, unknown> = {}) => ({
  event: "applied",
  id,
  success: true,
  current_value: null,
  requires_reboot: false,
  freed_bytes: null,
  size_after_bytes: null,
  ...extra,
});

const stored = (id: string) => useStore.getState().settings.get(id as never);

beforeEach(() => {
  bulkStreamApply.mockReset();
  vi.mocked(detectionManager.redetectSettings).mockClear();
  useStore.setState({
    settings: new Map(
      [
        action("cleanup:temp_files", "cleanup", "temp_files"),
        action("cleanup:docker_prune", "cleanup", "docker_prune"),
        action("cleanup:docker_prune_all", "cleanup", "docker_prune_all"),
        action("maintenance:ssd_retrim", "maintenance", "ssd_retrim", {
          currentValue: "overdue|23 days",
        }),
        action("timer:hpet", "timer", "hpet", {
          isAction: false,
          valueType: "choice",
          choices: ["enabled", "disabled"],
          currentValue: "enabled",
          recommendedValue: "disabled",
        }),
      ].map((s) => [s.id, s]),
    ),
    _settingsVersion: 0,
    cleanupResults: {},
    runSteps: [],
    operationStatus: {},
    bulkRun: null,
  } as never);
});

describe("an action in a run", () => {
  it("is run with true even when it would not be recommended unasked", () => {
    // The trap: deriving the value from `recommendedValue` skipped 24 of the 38
    // shipped actions (the backend reads a falsy action value as "do not run")
    // and reported success.
    const { sent } = startRun(["cleanup:temp_files"]);

    expect(sent()).toEqual({ "cleanup:temp_files": true });
  });

  it("gets a live step from the command's own output, and only for actions", () => {
    const { emit } = startRun(["cleanup:temp_files", "timer:hpet"]);
    expect(useStore.getState().runSteps.map((s) => s.id)).toEqual(["cleanup:temp_files"]);

    emit(started("cleanup:temp_files"));
    emit({ event: "output", id: "cleanup:temp_files", text: "Remove-Item $env:TEMP\\*", replaces: false });
    emit({ event: "output", id: "cleanup:temp_files", text: "Cleaned 400 MB", replaces: false, percent: 30 });

    const step = useStore.getState().runSteps[0];
    // The first line is the command itself, verbatim; the rest is its output.
    expect(step.status).toBe("running");
    expect(step.command).toBe("Remove-Item $env:TEMP\\*");
    expect(step.lines).toEqual(["Cleaned 400 MB"]);
    expect(step.percent).toBe(30);
  });
});

describe("the freed figure is the backend's measurement", () => {
  it("records what the run itself reported freeing", () => {
    const { emit } = startRun(["cleanup:temp_files"]);
    emit(started("cleanup:temp_files"));
    emit(applied("cleanup:temp_files", { freed_bytes: 400 * MB }));

    const recorded = useStore.getState().cleanupResults["cleanup:temp_files"];
    expect(recorded.success).toBe(true);
    expect(recorded.sized).toBe(true);
    expect(recorded.freedMB).toBe(400);
    expect(useStore.getState().runSteps[0].status).toBe("done");
  });

  it("keeps a fractional figure rather than rounding it away", () => {
    // Half a megabyte freed is still a measurement; the row's formatter is what
    // rounds it for display, so the store keeps what was measured.
    const { emit } = startRun(["cleanup:temp_files"]);
    emit(started("cleanup:temp_files"));
    emit(applied("cleanup:temp_files", { freed_bytes: 1536 * 1024 }));

    expect(useStore.getState().cleanupResults["cleanup:temp_files"].freedMB).toBe(1.5);
  });

  it("closes the row out without a number when the run measured no difference", () => {
    // Docker down, target gone, scan abandoned — or an action that reclaims
    // nothing at all. The cleanup still ran, so the row reports that rather than
    // a zero nobody measured (C11 rule 3).
    const { emit } = startRun(["cleanup:temp_files"]);
    emit(started("cleanup:temp_files"));
    emit(applied("cleanup:temp_files", { freed_bytes: null }));

    const recorded = useStore.getState().cleanupResults["cleanup:temp_files"];
    expect(recorded.success).toBe(true);
    expect(recorded.sized).toBe(false);
    expect(recorded.freedMB).toBeNull();
  });

  it("records a failure with its reason and no figure", () => {
    const { emit } = startRun(["cleanup:temp_files"]);
    emit(started("cleanup:temp_files"));
    emit({ event: "failed", id: "cleanup:temp_files", error: "Access to the path is denied" });

    const recorded = useStore.getState().cleanupResults["cleanup:temp_files"];
    expect(recorded).toMatchObject({
      success: false,
      freedMB: null,
      error: "Access to the path is denied",
    });
    expect(useStore.getState().runSteps[0].status).toBe("failed");
  });

  it("re-sizes the row from the reading taken after the run", () => {
    // Otherwise a finished cleanup keeps advertising the size it had before it
    // ran until the next poll happens to notice.
    const { emit } = startRun(["cleanup:temp_files"]);
    emit(applied("cleanup:temp_files", { freed_bytes: 400 * MB, size_after_bytes: 100 * MB }));

    expect(stored("cleanup:temp_files")?.currentValue).toBe("ready|100 MB");
  });

  it("leaves the row's size alone when nothing re-read it", () => {
    // A stale reading the poll will correct beats a fabricated one it cannot.
    const { emit } = startRun(["cleanup:temp_files"]);
    emit(applied("cleanup:temp_files", { size_after_bytes: null }));

    expect(stored("cleanup:temp_files")?.currentValue).toBe("ready|500 MB");
  });
});

describe("the reading a maintenance action reports when it finishes", () => {
  // `maintenance:ssd_retrim` answers `overdue|23 days` before it runs and
  // `ok|0 days` after; only `size_after_bytes` once reached the store, which no
  // maintenance action ever sends, so a retrim the user had just watched
  // succeed carried on saying it was overdue until the next detection pass.
  it("stores the state the run reported, so the row stops saying overdue", () => {
    const { emit } = startRun(["maintenance:ssd_retrim"]);
    emit(applied("maintenance:ssd_retrim", { current_value: "ok|0 days" }));

    expect(stored("maintenance:ssd_retrim")?.currentValue).toBe("ok|0 days");
  });

  it("says nothing about a state the run did not report", () => {
    // C11 rule 3: an action that came back without a reading leaves the last one
    // it had, rather than being credited with a state nobody read.
    const { emit } = startRun(["maintenance:ssd_retrim"]);
    emit(applied("maintenance:ssd_retrim", { current_value: null }));

    expect(stored("maintenance:ssd_retrim")?.currentValue).toBe("overdue|23 days");
  });
});

describe("docker", () => {
  it("reads the sibling prune's size again once one has run", () => {
    // One prune changes the other's reclaimable estimate, and the backend
    // invalidated both caches.
    const { emit } = startRun(["cleanup:docker_prune"]);
    emit(applied("cleanup:docker_prune", { freed_bytes: 1 * MB }));

    expect(detectionManager.redetectSettings).toHaveBeenCalledWith([
      "cleanup:docker_prune",
      "cleanup:docker_prune_all",
    ]);
  });

  it("does not re-read docker after an unrelated cleanup", () => {
    const { emit } = startRun(["cleanup:temp_files"]);
    emit(applied("cleanup:temp_files", { freed_bytes: 1 * MB }));

    expect(detectionManager.redetectSettings).not.toHaveBeenCalledWith(
      expect.arrayContaining(["cleanup:docker_prune"]),
    );
  });
});
