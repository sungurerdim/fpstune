/**
 * Tests for the useApply hook: one setting through POST /apply (MSW handlers) and
 * many over the one streamed path (settingsApi.bulkStreamApply is captured).
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useStore } from "../../store";
import { useApply } from "../useApply";
import { server } from "../../test/mocks/server";
import type { Setting } from "../../types/setting";
import { detectionManager } from "../../lib/detection-manager";

const { bulkStreamApply } = vi.hoisted(() => ({ bulkStreamApply: vi.fn() }));

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    settingsApi: {
      ...actual.settingsApi,
      // The stream is captured, not served: the tests below drive its events.
      bulkStreamApply: (...args: unknown[]) => bulkStreamApply(...args),
    },
  };
});

vi.mock("../../lib/detection-manager", () => ({
  detectionManager: {
    redetectSettings: vi.fn().mockResolvedValue(undefined),
    detectCategory: vi.fn().mockResolvedValue(undefined),
    detectAll: vi.fn().mockResolvedValue(undefined),
    stopAll: vi.fn(),
    initializeStore: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: {
    refreshMonitors: vi.fn(),
  },
}));

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "timer:hpet" as `${string}:${string}`,
    domain: "software",
    module: "timer",
    name: "hpet",
    displayName: "HPET",
    description: "High Precision Event Timer. Controls system timer source.",
    category: "core",
    valueType: "choice",
    choices: ["enabled", "disabled"],
    defaultValue: "enabled",
    recommendedValue: "disabled",
    requiresReboot: false,
    isAction: false,
    scope: "essential",
    currentImpact: "Enabled: higher latency",
    recommendedImpact: "Disabled: lower latency",
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

/** The detect shape an apply answers with after its re-detect (schemas.SettingState). */
function stateOf(current: unknown) {
  return {
    setting_id: "timer:hpet",
    current,
    applicable: true,
    applicable_reason: "",
    recommended: "disabled",
    default: "enabled",
    default_source: "windows_stock",
    is_optimized: current === "disabled",
    error: null,
    finding: null,
  };
}

// MSW uses decoded URL patterns; colons are literal in path patterns
const applyHandler = http.post("/api/settings/:id/apply", () =>
  HttpResponse.json({
    setting_id: "timer:hpet",
    success: true,
    error: null,
    state: stateOf("disabled"),
    requires_reboot: false,
  }),
);

describe("useApply", () => {
  beforeEach(() => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set("timer:hpet", makeSetting());
    useStore.setState({ settings, _settingsVersion: 0 });
    server.use(applyHandler);
  });

  it("returns the apply/reset/run functions and the isPending helper", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });

    expect(typeof result.current.apply).toBe("function");
    expect(typeof result.current.reset).toBe("function");
    expect(typeof result.current.run).toBe("function");
    expect(typeof result.current.isPending).toBe("function");
    expect(result.current.isPending("timer:hpet")).toBe(false);
    expect(result.current.pendingIds.size).toBe(0);
  });

  it("marks setting as pending during apply and removes it after", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });
    const setting = makeSetting();

    let applyPromise!: Promise<unknown>;
    act(() => {
      applyPromise = result.current.apply(setting, "disabled");
    });

    // Should be pending immediately after starting
    expect(result.current.isPending("timer:hpet")).toBe(true);

    await act(async () => {
      await applyPromise;
    });

    expect(result.current.isPending("timer:hpet")).toBe(false);
  });

  it("a successful apply produces a visible confirmation (E8)", async () => {
    // The defect: applying a tweak from Home changed the machine with no
    // on-screen acknowledgement at all — the only trace was the row's badge.
    useStore.setState({ notifications: [] } as never);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply(makeSetting(), "disabled");
    });

    const notifications = useStore.getState().notifications;
    expect(
      notifications.some(
        (n) => n.type === "success" && n.message === "Applied HPET",
      ),
    ).toBe(true);
  });

  it("a failed apply says so, with the backend's reason (E8)", async () => {
    useStore.setState({ notifications: [] } as never);
    server.use(
      http.post("/api/settings/:id/apply", () =>
        HttpResponse.json({
          setting_id: "timer:hpet",
          success: false,
          error: "registry key is access-denied",
          state: null,
          requires_reboot: false,
        }),
      ),
    );
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply(makeSetting(), "disabled");
    });

    const notifications = useStore.getState().notifications;
    expect(
      notifications.some(
        (n) =>
          n.type === "error" &&
          n.message.includes("registry key is access-denied"),
      ),
    ).toBe(true);
  });

  it("updates store with state.current on successful apply", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });
    const setting = makeSetting();

    await act(async () => {
      await result.current.apply(setting, "disabled");
    });

    const updated = useStore.getState().settings.get("timer:hpet");
    expect(updated?.currentValue).toBe("disabled");
    // The backend's verdict, carried as it came.
    expect(updated?.isOptimized).toBe(true);
  });

  it("returns the response object from apply", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });
    const setting = makeSetting();

    let response: unknown;
    await act(async () => {
      response = await result.current.apply(setting, "disabled");
    });

    expect(response).toMatchObject({
      success: true,
      state: { current: "disabled" },
    });
  });

  it("still clears pending on API failure", async () => {
    server.use(
      http.post("/api/settings/:id/apply", () =>
        HttpResponse.json({ detail: "Internal server error" }, { status: 500 }),
      ),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });
    const setting = makeSetting();

    await act(async () => {
      try {
        await result.current.apply(setting, "disabled");
      } catch {
        // expected
      }
    });

    await waitFor(() => {
      expect(result.current.isPending("timer:hpet")).toBe(false);
    });
  });

  it("reset applies the setting's own default through /apply — there is no reset endpoint", async () => {
    // The defect this guards: a reset posted to its own route, so the backend
    // carried a second write path (and a second idea of "correct") beside apply.
    const seen: { url: string; body: unknown }[] = [];
    server.use(
      http.post("/api/settings/:id/apply", async ({ request }) => {
        seen.push({ url: new URL(request.url).pathname, body: await request.json() });
        return HttpResponse.json({
          setting_id: "timer:hpet",
          success: true,
          error: null,
          state: stateOf("enabled"),
          requires_reboot: false,
          verified: true,
        });
      }),
    );
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.reset(makeSetting({ defaultValue: "enabled" }));
    });

    expect(seen).toEqual([
      { url: "/api/settings/timer:hpet/apply", body: { value: "enabled" } },
    ]);
    const updated = useStore.getState().settings.get("timer:hpet");
    expect(updated?.currentValue).toBe("enabled");
    expect(updated?.isOptimized).toBe(false);
  });

  it("isPending is false for unrelated setting id", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });
    expect(result.current.isPending("power:usb")).toBe(false);
  });

  it("takes is_optimized from the backend's state, never from current vs recommended", async () => {
    // The defect this guards: the hook recomputed `valuesEqual(current,
    // recommendedValue)`, so a row whose backend verdict differed from that
    // comparison (a tolerance the backend applies, a recommendation that moved)
    // showed the frontend's opinion. Here current === recommended but the
    // backend says not optimized, and the reverse on a second row.
    server.use(
      http.post("/api/settings/:id/apply", () =>
        HttpResponse.json({
          setting_id: "timer:hpet",
          success: true,
          error: null,
          state: { ...stateOf("disabled"), is_optimized: false },
          requires_reboot: false,
          verified: true,
        }),
      ),
    );
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply(makeSetting(), "disabled");
    });
    expect(useStore.getState().settings.get("timer:hpet")?.isOptimized).toBe(false);
    expect(useStore.getState().settings.get("timer:hpet")?.status).toBe("suboptimal");

    server.use(
      http.post("/api/settings/:id/apply", () =>
        HttpResponse.json({
          setting_id: "timer:hpet",
          success: true,
          error: null,
          state: { ...stateOf("enabled"), is_optimized: true },
          requires_reboot: false,
          verified: true,
        }),
      ),
    );
    await act(async () => {
      await result.current.apply(makeSetting(), "enabled");
    });
    expect(useStore.getState().settings.get("timer:hpet")?.isOptimized).toBe(true);
    expect(useStore.getState().settings.get("timer:hpet")?.status).toBe("optimal");
  });

  it("feeds the default and whose stock it is from the apply's state", async () => {
    server.use(
      http.post("/api/settings/:id/apply", () =>
        HttpResponse.json({
          setting_id: "timer:hpet",
          success: true,
          error: null,
          state: { ...stateOf("disabled"), default: "auto", default_source: "driver" },
          requires_reboot: false,
          verified: true,
        }),
      ),
    );
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply(makeSetting(), "disabled");
    });

    const updated = useStore.getState().settings.get("timer:hpet");
    expect(updated?.defaultValue).toBe("auto");
    expect(updated?.defaultSource).toBe("driver");
  });
});

describe("useApply.run (bulk over the one stream)", () => {
  const redetect = vi.mocked(detectionManager.redetectSettings);

  beforeEach(() => {
    bulkStreamApply.mockReset();
    bulkStreamApply.mockImplementation(() => () => {});
    redetect.mockClear();
    useStore.setState({
      settings: new Map([
        ["timer:hpet", makeSetting()],
        ["power:usb", makeSetting({ id: "power:usb" as `${string}:${string}`, recommendedValue: "off", defaultValue: "on" })],
      ]),
      operationStatus: {},
      operationError: {},
      bulkRun: null,
      notifications: [],
    } as never);
  });

  it("sends one stream request carrying {id: value}, apply = recommendation, reset = default", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });

    act(() => result.current.run("apply", ["timer:hpet", "power:usb"]));
    expect(bulkStreamApply).toHaveBeenCalledTimes(1);
    expect(bulkStreamApply.mock.calls[0][0]).toEqual({
      "timer:hpet": "disabled",
      "power:usb": "off",
    });
    expect(result.current.isRunning).toBe(true);

    // A run is in flight: a second one must not start over it.
    act(() => result.current.run("reset", ["timer:hpet"]));
    expect(bulkStreamApply).toHaveBeenCalledTimes(1);

    act(() => result.current.stop());
    act(() => result.current.run("reset", ["timer:hpet", "power:usb"]));
    expect(bulkStreamApply.mock.calls[1][0]).toEqual({
      "timer:hpet": "enabled",
      "power:usb": "on",
    });
  });

  it("shows each row's outcome as it streams, then re-detects every id once", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });
    act(() => result.current.run("apply", ["timer:hpet", "power:usb"]));
    const onEvent = bulkStreamApply.mock.calls[0][1] as (e: Record<string, unknown>) => void;
    const onDone = bulkStreamApply.mock.calls[0][2] as () => void;

    act(() => onEvent({ event: "started", id: "timer:hpet" }));
    expect(useStore.getState().operationStatus["timer:hpet"]).toBe("running");
    act(() => {
      onEvent({ event: "verified", id: "timer:hpet", matches: true, current_value: "disabled" });
      onEvent({ event: "failed", id: "power:usb", error: "access denied" });
    });
    expect(useStore.getState().operationStatus["timer:hpet"]).toBe("verified");
    expect(useStore.getState().operationStatus["power:usb"]).toBe("failed");
    // The stream carries the read-back but not the verdict, so the store's
    // verdict is untouched until the re-detect: nothing was recomputed here.
    expect(useStore.getState().settings.get("timer:hpet")?.isOptimized).toBe(false);
    expect(redetect).not.toHaveBeenCalled();

    act(() => onDone());
    expect(redetect).toHaveBeenCalledTimes(1);
    expect(redetect).toHaveBeenCalledWith(["timer:hpet", "power:usb"]);
    expect(useStore.getState().bulkRun).toBeNull();
    expect(
      useStore.getState().notifications.some((n) => n.type === "warning" && n.message === "1 done, 1 failed."),
    ).toBe(true);
  });

  it("marks every row the stream never reached as failed, with the reason, when it dies", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApply(), { wrapper: Wrapper });
    act(() => result.current.run("apply", ["timer:hpet", "power:usb"]));
    const onError = bulkStreamApply.mock.calls[0][3] as (e: unknown) => void;

    act(() => onError(new Error("connection reset")));

    expect(useStore.getState().operationStatus["timer:hpet"]).toBe("failed");
    expect(useStore.getState().operationStatus["power:usb"]).toBe("failed");
    expect(useStore.getState().bulkRun).toBeNull();
    expect(redetect).toHaveBeenCalledWith(["timer:hpet", "power:usb"]);
  });
});
