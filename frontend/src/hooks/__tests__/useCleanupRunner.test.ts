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

/**
 * One cleanup that ran, reported its command, and verified.
 *
 * `applied` carries the backend's own readings either side of the run:
 * `freed_bytes` is the difference it measured, `size_after_bytes` what is still
 * reclaimable. Both default to absent — the shape of an action that reclaims
 * nothing, or one whose size could not be re-read.
 */
const successEvents = (
  id = "cleanup:temp_files",
  applied: Record<string, unknown> = {},
) => [
  { event: "started", id, name: "Temp Files", duration_estimate: "", reports_progress: false },
  { event: "output", id, text: "Remove-Item -Recurse -Force $env:TEMP\\*", replaces: false },
  { event: "output", id, text: "Cleaned 400 MB", replaces: false },
  {
    event: "applied",
    id,
    success: true,
    current_value: null,
    requires_reboot: false,
    freed_bytes: null,
    size_after_bytes: null,
    ...applied,
  },
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

  // The freed-space figure is the product this feature exists to show, and the
  // frontend no longer computes it. It used to snapshot the size before a run,
  // wait for the size poll to notice a change, and subtract — which missed the
  // change whenever the re-measure landed first, leaving the row spinning on a
  // number that had already settled. Only the backend knows both readings
  // belong to the same run, so it takes them and reports the difference.
  describe("the freed figure is the backend's measurement", () => {
    const MB = 1024 * 1024;

    it("records what the run itself reported freeing", async () => {
      server.use(
        streamHandler(
          successEvents("cleanup:temp_files", { freed_bytes: 400 * MB }),
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
        expect(recorded?.sized).toBe(true);
        expect(recorded?.freedMB).toBe(400);
      });
    });

    it("keeps a fractional figure rather than rounding it away", async () => {
      // Half a megabyte freed is still a measurement; the row's formatter is
      // what rounds it for display, so the store keeps what was measured.
      server.use(
        streamHandler(
          successEvents("cleanup:temp_files", { freed_bytes: 1536 * 1024 }),
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
        expect(
          useStore.getState().cleanupResults["cleanup:temp_files"]?.freedMB,
        ).toBe(1.5);
      });
    });

    it("closes the row out when the run measured no difference", async () => {
      // Docker down, target gone, scan abandoned — or an action that reclaims
      // nothing at all. The cleanup still ran, so the row reports that rather
      // than a zero nobody measured (C11 rule 3).
      server.use(
        streamHandler(
          successEvents("cleanup:temp_files", { freed_bytes: null }),
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

    it("re-sizes the row from the reading taken after the run", async () => {
      // Otherwise a finished cleanup keeps advertising the size it had before
      // it ran until the next poll happens to notice.
      server.use(
        streamHandler(
          successEvents("cleanup:temp_files", {
            freed_bytes: 400 * MB,
            size_after_bytes: 100 * MB,
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
        expect(
          useStore.getState().settings.get("cleanup:temp_files")?.currentValue,
        ).toBe("ready|100 MB");
      });
    });

    it("leaves the row's size alone when nothing re-read it", async () => {
      server.use(
        streamHandler(
          successEvents("cleanup:temp_files", { size_after_bytes: null }),
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
        expect(result.current.isRunning).toBe(false);
      });
      // The fixture's pre-run size, untouched: a stale reading the poll will
      // correct beats a fabricated one it cannot.
      expect(
        useStore.getState().settings.get("cleanup:temp_files")?.currentValue,
      ).toBe("ready|500 MB");
    });
  });

  /**
   * A maintenance action reports a state, not a byte count.
   *
   * `maintenance:ssd_retrim` answers `overdue|23 days` before it runs and
   * `ok|0 days` after — and until this existed the runner stored neither, so a
   * retrim the user had just watched succeed carried on saying it was overdue
   * until the next full detection pass. Only `size_after_bytes` reached the
   * store, which no maintenance action ever sends.
   */
  describe("the reading a maintenance action reports when it finishes", () => {
    beforeEach(() => {
      const settings = useStore.getState().settings;
      settings.set(
        "maintenance:ssd_retrim",
        makeActionSetting(
          "maintenance:ssd_retrim",
          "maintenance",
          "ssd_retrim",
          { category: "maintenance", currentValue: "overdue|23 days" },
        ),
      );
      useStore.setState({ settings: new Map(settings), _settingsVersion: 1 });
    });

    it("stores the state the run reported, so the row stops saying overdue", async () => {
      server.use(
        streamHandler(
          successEvents("maintenance:ssd_retrim", {
            current_value: "ok|0 days",
            freed_bytes: null,
            size_after_bytes: null,
          }),
        ),
      );

      const { Wrapper } = makeWrapper();
      const { result } = renderHook(
        () => useCleanupRunner({ modules: ["maintenance"] }),
        { wrapper: Wrapper },
      );

      await act(async () => {
        result.current.run(["maintenance:ssd_retrim"]);
      });

      await waitFor(() => {
        expect(
          useStore.getState().settings.get("maintenance:ssd_retrim")
            ?.currentValue,
        ).toBe("ok|0 days");
      });
    });

    it("says nothing about a state the run did not report", async () => {
      // C11 rule 3: an action that came back without a reading leaves the last
      // one it had, rather than being credited with a state nobody read.
      server.use(
        streamHandler(
          successEvents("maintenance:ssd_retrim", {
            current_value: null,
            freed_bytes: null,
            size_after_bytes: null,
          }),
        ),
      );

      const { Wrapper } = makeWrapper();
      const { result } = renderHook(
        () => useCleanupRunner({ modules: ["maintenance"] }),
        { wrapper: Wrapper },
      );

      await act(async () => {
        result.current.run(["maintenance:ssd_retrim"]);
      });

      await waitFor(() => {
        expect(result.current.isRunning).toBe(false);
      });
      expect(
        useStore.getState().settings.get("maintenance:ssd_retrim")
          ?.currentValue,
      ).toBe("overdue|23 days");
    });
  });
});
