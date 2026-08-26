/**
 * Tests for useApplySingle hook.
 * Mocks settingsApi.applySetting via MSW local server.use() handlers.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useStore } from "../../store";
import { useApplySingle } from "../useApplySingle";
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

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: {
    refreshMonitors: vi.fn(),
  },
}));

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "timer:hpet" as `${string}:${string}`,
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

// MSW uses decoded URL patterns; colons are literal in path patterns
const applyHandler = http.post("/api/settings/:id/apply", () =>
  HttpResponse.json({
    setting_id: "timer:hpet",
    success: true,
    error: null,
    new_value: "disabled",
    requires_reboot: false,
  }),
);

describe("useApplySingle", () => {
  beforeEach(() => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set("timer:hpet", makeSetting());
    useStore.setState({ settings, _settingsVersion: 0 });
    server.use(applyHandler);
  });

  it("returns applySingle function and isPending helper", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApplySingle(), { wrapper: Wrapper });

    expect(typeof result.current.applySingle).toBe("function");
    expect(typeof result.current.isPending).toBe("function");
    expect(result.current.isPending("timer:hpet")).toBe(false);
    expect(result.current.pendingIds.size).toBe(0);
  });

  it("marks setting as pending during apply and removes it after", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApplySingle(), { wrapper: Wrapper });
    const setting = makeSetting();

    let applyPromise!: Promise<unknown>;
    act(() => {
      applyPromise = result.current.applySingle(setting, "disabled");
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
    const { result } = renderHook(() => useApplySingle(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.applySingle(makeSetting(), "disabled");
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
          new_value: null,
          requires_reboot: false,
        }),
      ),
    );
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApplySingle(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.applySingle(makeSetting(), "disabled");
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

  it("updates store with new_value on successful apply", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApplySingle(), { wrapper: Wrapper });
    const setting = makeSetting();

    await act(async () => {
      await result.current.applySingle(setting, "disabled");
    });

    const updated = useStore.getState().settings.get("timer:hpet");
    expect(updated?.currentValue).toBe("disabled");
    // "disabled" === "disabled" (recommendedValue) → isOptimized should be true
    expect(updated?.isOptimized).toBe(true);
  });

  it("returns the response object from applySingle", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApplySingle(), { wrapper: Wrapper });
    const setting = makeSetting();

    let response: unknown;
    await act(async () => {
      response = await result.current.applySingle(setting, "disabled");
    });

    expect(response).toMatchObject({ success: true, new_value: "disabled" });
  });

  it("still clears pending on API failure", async () => {
    server.use(
      http.post("/api/settings/:id/apply", () =>
        HttpResponse.json({ detail: "Internal server error" }, { status: 500 }),
      ),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApplySingle(), { wrapper: Wrapper });
    const setting = makeSetting();

    await act(async () => {
      try {
        await result.current.applySingle(setting, "disabled");
      } catch {
        // expected
      }
    });

    await waitFor(() => {
      expect(result.current.isPending("timer:hpet")).toBe(false);
    });
  });

  it("isPending is false for unrelated setting id", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useApplySingle(), { wrapper: Wrapper });
    expect(result.current.isPending("power:usb")).toBe(false);
  });
});
