/**
 * Tests for useBulkApply hook.
 * The hook runs the one bulk path (the SSE stream) and assembles its outcome;
 * MSW answers `/settings/bulk/stream-apply` with the real wire format.
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

/** The wire format the app speaks: one SSE `data:` line per event. */
function sseBody(events: Array<Record<string, unknown>>): string {
  return events.map((event) => `data: ${JSON.stringify(event)}

`).join("");
}

function streamHandler(
  events: Array<Record<string, unknown>>,
  seen?: { body?: unknown },
) {
  return http.post("/api/settings/bulk/stream-apply", async ({ request }) => {
    if (seen) seen.body = await request.json();
    return new HttpResponse(sseBody(events), {
      headers: { "Content-Type": "text/event-stream" },
    });
  });
}

const appliedAndVerified = (id: string) => [
  { event: "started", id, name: id, duration_estimate: "", reports_progress: false },
  {
    event: "applied",
    id,
    success: true,
    current_value: "disabled",
    requires_reboot: false,
    freed_bytes: null,
    size_after_bytes: null,
  },
  { event: "verified", id, matches: true, current_value: "disabled" },
];

const bothApplied = [
  ...appliedAndVerified("timer:hpet"),
  ...appliedAndVerified("power:usb"),
  { event: "done", total: 2, succeeded: 2, failed: 0 },
];

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

    server.use(streamHandler(bothApplied));
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
      http.post("/api/settings/bulk/stream-apply", () =>
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

  it("sends the map to the stream as {settings: {id: value}} and nothing else", async () => {
    const seen: { body?: unknown } = {};
    server.use(streamHandler(bothApplied, seen));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply({
        "timer:hpet": "disabled",
        "power:usb": "disabled",
      });
    });

    expect(seen.body).toEqual({
      settings: { "timer:hpet": "disabled", "power:usb": "disabled" },
    });
  });

  it("counts a failed row as an error and a skipped one as neither", async () => {
    server.use(
      streamHandler([
        ...appliedAndVerified("timer:hpet"),
        { event: "skipped", id: "gpu:nvidia_extra" },
        { event: "failed", id: "power:usb", error: "Access denied" },
        { event: "done", total: 3, succeeded: 2, failed: 1 },
      ]),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply({
        "timer:hpet": "disabled",
        "gpu:nvidia_extra": "disabled",
        "power:usb": "disabled",
      });
    });

    await waitFor(() => {
      expect(result.current.lastResult).not.toBeNull();
    });

    // One written, one failed; the skipped row is neither (it was not applicable).
    expect(result.current.lastResult).toEqual({ success: 1, error: 1 });
  });

  it("counts a skipped row as no error at all", async () => {
    server.use(
      streamHandler([
        ...appliedAndVerified("timer:hpet"),
        { event: "skipped", id: "gpu:nvidia_extra" },
        { event: "done", total: 2, succeeded: 2, failed: 0 },
      ]),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkApply(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.apply({
        "timer:hpet": "disabled",
        "gpu:nvidia_extra": "disabled",
      });
    });

    await waitFor(() => {
      expect(result.current.lastResult).not.toBeNull();
    });

    // The old arithmetic subtracted skipped rows from an error count that never
    // held them, which read one skipped row as -1 failures.
    expect(result.current.lastResult).toEqual({ success: 1, error: 0 });
  });
});
