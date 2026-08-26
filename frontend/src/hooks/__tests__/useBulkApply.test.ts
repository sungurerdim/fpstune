/**
 * Tests for useBulkApply hook.
 * Mocks settingsApi.bulkApply via MSW local server.use() handlers.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useStore } from "../../store";
import { useBulkApply } from "../useBulkApply";
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

const bulkApplySuccessResponse = {
  results: {
    "timer:hpet": {
      setting_id: "timer:hpet",
      success: true,
      error: null,
      new_value: "disabled",
      requires_reboot: false,
      skipped: false,
    },
    "power:usb": {
      setting_id: "power:usb",
      success: true,
      error: null,
      new_value: "disabled",
      requires_reboot: false,
      skipped: false,
    },
  },
  success_count: 2,
  error_count: 0,
  requires_reboot: false,
};

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { Wrapper, queryClient };
}

describe("useBulkApply", () => {
  beforeEach(() => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set("timer:hpet", makeSetting({ id: "timer:hpet" as `${string}:${string}` }));
    settings.set(
      "power:usb",
      makeSetting({
        id: "power:usb" as `${string}:${string}`,
        module: "power",
        name: "usb",
      }),
    );
    useStore.setState({ settings, _settingsVersion: 0 });

    server.use(
      http.post("/api/settings/bulk/apply", () =>
        HttpResponse.json(bulkApplySuccessResponse),
      ),
    );
  });

  it("returns apply function, isApplying=false, and lastResult=null initially", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkApply(), { wrapper: Wrapper });

    expect(typeof result.current.apply).toBe("function");
    expect(result.current.isApplying).toBe(false);
    expect(result.current.lastResult).toBeNull();
  });

  it("sets isApplying=false after apply completes", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply({ "timer:hpet": "disabled" });
    });

    expect(result.current.isApplying).toBe(false);
  });

  it("sets lastResult with success count after successful bulk apply", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply({
        "timer:hpet": "disabled",
        "power:usb": "disabled",
      });
    });

    await waitFor(() => {
      expect(result.current.lastResult).not.toBeNull();
    });

    expect(result.current.lastResult?.success).toBe(2);
    expect(result.current.lastResult?.error).toBe(0);
  });

  it("calls onSuccess callback when apply succeeds", async () => {
    const onSuccess = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkApply({ onSuccess }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.apply({ "timer:hpet": "disabled" });
    });

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
    expect(onSuccess).toHaveBeenCalledWith(
      expect.objectContaining({ success_count: 2 }),
    );
  });

  it("calls onError callback when apply fails", async () => {
    server.use(
      http.post("/api/settings/bulk/apply", () =>
        HttpResponse.json({ detail: "Server error" }, { status: 500 }),
      ),
    );

    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkApply({ onError }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      try {
        await result.current.apply({ "timer:hpet": "disabled" });
      } catch {
        // expected to throw
      }
    });

    await waitFor(() => {
      expect(onError).toHaveBeenCalledTimes(1);
    });
  });

  it("counts real errors excluding skipped settings", async () => {
    server.use(
      http.post("/api/settings/bulk/apply", () =>
        HttpResponse.json({
          results: {
            "timer:hpet": {
              setting_id: "timer:hpet",
              success: true,
              error: null,
              new_value: "disabled",
              requires_reboot: false,
              skipped: false,
            },
            "gpu:nvidia_extra": {
              setting_id: "gpu:nvidia_extra",
              success: false,
              error: "Not applicable",
              new_value: null,
              requires_reboot: false,
              skipped: true, // Skipped, not a real error
            },
          },
          success_count: 1,
          error_count: 1,
          requires_reboot: false,
        }),
      ),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply({ "timer:hpet": "disabled" });
    });

    await waitFor(() => {
      expect(result.current.lastResult).not.toBeNull();
    });

    // skipped entries are excluded from real error count
    expect(result.current.lastResult?.error).toBe(0);
  });
});
