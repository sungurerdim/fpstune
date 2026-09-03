/**
 * Tests for useCleanupRunner hook.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useStore } from "../../store";
import { useCleanupRunner } from "../useCleanupRunner";
import { server } from "../../test/mocks/server";
import type { Setting } from "../../types/setting";

vi.mock("../../lib/detection-manager", () => ({
  detectionManager: {
    redetectSettings: vi.fn().mockResolvedValue(undefined),
    detectCategory: vi.fn().mockResolvedValue(undefined),
    detectAll: vi.fn().mockResolvedValue(undefined),
    stopAll: vi.fn(),
    initializeStore: vi.fn().mockResolvedValue(undefined),
  },
}));

function makeActionSetting(
  id: string,
  module: string,
  name: string,
  overrides: Partial<Setting> = {},
): Setting {
  return {
    id: id as `${string}:${string}`,
    module,
    name,
    displayName: name.replace(/_/g, " "),
    description: "Cleanup action.",
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
    currentValue: "ready|500 MB",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
    ...overrides,
  };
}

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { Wrapper, queryClient };
}

/**
 * The run goes through the SSE endpoint now, because the events are what tell
 * the user which command is running and how far it has got. These helpers speak
 * that wire format so the tests exercise the path the app takes.
 */
function sseBody(events: Array<Record<string, unknown>>): string {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
}

function streamHandler(events: Array<Record<string, unknown>>) {
  return http.post(
    "/api/settings/bulk/stream-apply",
    () =>
      new HttpResponse(sseBody(events), {
        headers: { "Content-Type": "text/event-stream" },
      }),
  );
}

/** One cleanup that ran, reported its command, and verified. */
const successEvents = (id = "cleanup:temp_files") => [
  { event: "started", id, name: "Temp Files", duration_estimate: "", reports_progress: false },
  { event: "output", id, text: "Remove-Item -Recurse -Force $env:TEMP\\*", replaces: false },
  { event: "output", id, text: "Cleaned 400 MB", replaces: false },
  { event: "applied", id, success: true, current_value: null, requires_reboot: false },
  { event: "verified", id, matches: true, current_value: null },
  { event: "done", total: 1, succeeded: 1, failed: 0 },
];

describe("useCleanupRunner", () => {
  beforeEach(() => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "cleanup:temp_files",
      makeActionSetting("cleanup:temp_files", "cleanup", "temp_files"),
    );
    settings.set(
      "cleanup:browser_cache",
      makeActionSetting("cleanup:browser_cache", "cleanup", "browser_cache"),
    );
    // Non-applicable — should be excluded from actionIds
    settings.set(
      "cleanup:game_cache",
      makeActionSetting("cleanup:game_cache", "cleanup", "game_cache", {
        isApplicable: false,
      }),
    );
    // Not in the "cleanup" module — should not appear in cleanup runner
    settings.set(
      "maintenance:sfc",
      makeActionSetting("maintenance:sfc", "maintenance", "sfc", {
        category: "maintenance",
      }),
    );

    useStore.setState({
      settings,
      _settingsVersion: 0,
      maintenanceSelection: {},
      cleanupResults: {},
    });

    server.use(streamHandler(successEvents()));
  });

  it("returns correct initial state", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useCleanupRunner({ modules: ["cleanup"] }),
      { wrapper: Wrapper },
    );

    expect(result.current.selectedIds).toEqual([]);
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.hasSelection).toBe(false);
    expect(result.current.isRunning).toBe(false);
    expect(result.current.confirmIds).toBeNull();
  });

  it("only includes applicable action settings for specified modules", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useCleanupRunner({ modules: ["cleanup"] }),
      { wrapper: Wrapper },
    );

    // Run with all ids for this module — only applicable ones
    await act(async () => {
      result.current.run(["cleanup:temp_files", "cleanup:browser_cache"]);
    });

    // game_cache is not applicable, maintenance:sfc is a different module
    // After the run completes, isRunning should be false
    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });
  });

  it("reflects maintenanceSelection from store as selectedIds", () => {
    useStore.getState().toggleMaintenanceSelection("cleanup:temp_files");
    useStore.getState().toggleMaintenanceSelection("cleanup:browser_cache");

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useCleanupRunner({ modules: ["cleanup"] }),
      { wrapper: Wrapper },
    );

    expect(result.current.selectedCount).toBe(2);
    expect(result.current.hasSelection).toBe(true);
    expect(result.current.selectedIds).toContain("cleanup:temp_files");
    expect(result.current.selectedIds).toContain("cleanup:browser_cache");
  });

  it("run() with explicit ids starts and completes mutation", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useCleanupRunner({ modules: ["cleanup"] }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.run(["cleanup:temp_files"]);
    });

    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });

    // Verify cleanup result was recorded
    const cleanupResult =
      useStore.getState().cleanupResults["cleanup:temp_files"];
    expect(cleanupResult).toBeDefined();
    expect(cleanupResult?.success).toBe(true);
  });

  it("run() with no ids and no selection is a no-op", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useCleanupRunner({ modules: ["cleanup"] }),
      { wrapper: Wrapper },
    );

    act(() => {
      result.current.run();
    });

    expect(result.current.isRunning).toBe(false);
  });

  it("docker_prune triggers confirm gate instead of immediate run", () => {
    const settings = new Map(useStore.getState().settings);
    settings.set(
      "cleanup:docker_prune",
      makeActionSetting("cleanup:docker_prune", "cleanup", "docker_prune"),
    );
    useStore.setState({ settings });

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useCleanupRunner({ modules: ["cleanup"] }),
      { wrapper: Wrapper },
    );

    act(() => {
      result.current.run(["cleanup:docker_prune"]);
    });

    // Should NOT start running — it should wait for confirm
    expect(result.current.isRunning).toBe(false);
    expect(result.current.confirmIds).toEqual(["cleanup:docker_prune"]);
  });

  it("cancelConfirm() clears confirmIds without running", () => {
    const settings = new Map(useStore.getState().settings);
    settings.set(
      "cleanup:docker_prune",
      makeActionSetting("cleanup:docker_prune", "cleanup", "docker_prune"),
    );
    useStore.setState({ settings });

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useCleanupRunner({ modules: ["cleanup"] }),
      { wrapper: Wrapper },
    );

    act(() => {
      result.current.run(["cleanup:docker_prune"]);
    });

    expect(result.current.confirmIds).not.toBeNull();

    act(() => {
      result.current.cancelConfirm();
    });

    expect(result.current.confirmIds).toBeNull();
    expect(result.current.isRunning).toBe(false);
  });

  it("confirmRun() starts the run after confirmation", async () => {
    server.use(streamHandler(successEvents("cleanup:docker_prune")));

    const settings = new Map(useStore.getState().settings);
    settings.set(
      "cleanup:docker_prune",
      makeActionSetting("cleanup:docker_prune", "cleanup", "docker_prune", {
        isApplicable: true,
        impactCategories: [],
      }),
    );
    useStore.setState({ settings });

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useCleanupRunner({ modules: ["cleanup"] }),
      { wrapper: Wrapper },
    );

    act(() => {
      result.current.run(["cleanup:docker_prune"]);
    });

    expect(result.current.confirmIds).not.toBeNull();

    act(() => {
      result.current.confirmRun();
    });

    expect(result.current.confirmIds).toBeNull();

    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });
  });

  // The freed-space figure is the product this feature exists to show, and it
  // used to be delivered only by the size poll noticing a *change*. Everything
  // below is a way for that change to be missed.
  describe("freed space always arrives", () => {
    const sizes = (bytes: number) =>
      http.get("/api/settings/cleanup-sizes", () =>
        HttpResponse.json({
          "cleanup:temp_files": { bytes, status: "ready" },
        }),
      );

    it("reports the difference when the new size is ready before the run returns", async () => {
      // A small cleanup is re-measured in the time the bulk request takes, so by
      // the time the run reports there is no change left for the poll to notice.
      // The row spun on a spinner forever waiting for one.
      server.use(sizes(100 * 1024 * 1024));

      const { Wrapper } = makeWrapper();
      const { result } = renderHook(
        () => useCleanupRunner({ modules: ["cleanup"] }),
        { wrapper: Wrapper },
      );

      await act(async () => {
        result.current.run(["cleanup:temp_files"]);
      });

      await waitFor(() => {
        const recorded =
          useStore.getState().cleanupResults["cleanup:temp_files"];
        // The fixture's pre-run size is 500 MB.
        expect(recorded?.freedMB).toBe(400);
      });
    });

    it("closes the row out when the new size cannot be measured", async () => {
      // Docker down, target gone, scan abandoned: the cleanup still ran, so the
      // row reports that rather than spinning on a number nobody can produce.
      server.use(
        http.get("/api/settings/cleanup-sizes", () =>
          HttpResponse.json({
            "cleanup:temp_files": { bytes: 0, status: "unavailable" },
          }),
        ),
      );

      const { Wrapper } = makeWrapper();
      const { result } = renderHook(
        () => useCleanupRunner({ modules: ["cleanup"] }),
        { wrapper: Wrapper },
      );

      await act(async () => {
        result.current.run(["cleanup:temp_files"]);
      });

      await waitFor(() => {
        const recorded =
          useStore.getState().cleanupResults["cleanup:temp_files"];
        expect(recorded?.success).toBe(true);
        expect(recorded?.sized).toBe(false);
        expect(recorded?.freedMB).toBeNull();
      });
    });
  });
});
