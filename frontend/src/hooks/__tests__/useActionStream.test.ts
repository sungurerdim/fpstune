/**
 * Tests for useActionStream hook.
 * Uses a mock EventSource since jsdom doesn't implement SSE.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useActionStream } from "../useActionStream";

// EventSource mock with controllable message dispatch
interface MockEventSourceInstance {
  url: string;
  onmessage: ((e: { data: string }) => void) | null;
  onerror: ((e: Event) => void) | null;
  close: ReturnType<typeof vi.fn>;
  _dispatchMessage: (data: object) => void;
  _dispatchError: () => void;
}

let lastEventSource: MockEventSourceInstance | null = null;

class MockEventSource {
  url: string;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    lastEventSource = this as unknown as MockEventSourceInstance;
  }

  _dispatchMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  _dispatchError() {
    this.onerror?.(new Event("error"));
  }
}

describe("useActionStream", () => {
  beforeEach(() => {
    lastEventSource = null;
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts in idle state", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    expect(result.current.isRunning).toBe(false);
    expect(result.current.output).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(result.current.success).toBeNull();
  });

  it("execute() opens EventSource and sets isRunning=true", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    act(() => {
      result.current.execute();
    });

    expect(result.current.isRunning).toBe(true);
    expect(lastEventSource).not.toBeNull();
    expect(lastEventSource!.url).toContain("maintenance%3Asfc");
  });

  it("appends output lines from 'output' events", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    act(() => {
      result.current.execute();
    });

    act(() => {
      lastEventSource!._dispatchMessage({
        type: "output",
        line: "Scanning system files...",
        progress: 0,
        success: false,
        error: "",
      });
    });

    expect(result.current.output).toContain("Scanning system files...");
  });

  it("keeps only last 10 output lines", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    act(() => {
      result.current.execute();
    });

    act(() => {
      for (let i = 0; i < 15; i++) {
        lastEventSource!._dispatchMessage({
          type: "output",
          line: `Line ${i}`,
          progress: 0,
          success: false,
          error: "",
        });
      }
    });

    expect(result.current.output).toHaveLength(10);
    // Should contain the last 10 lines (5-14)
    expect(result.current.output[0]).toBe("Line 5");
    expect(result.current.output[9]).toBe("Line 14");
  });

  it("sets success=true and isRunning=false on complete event with success=true", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    act(() => {
      result.current.execute();
    });

    act(() => {
      lastEventSource!._dispatchMessage({
        type: "complete",
        line: "",
        progress: 100,
        success: true,
        error: "",
      });
    });

    expect(result.current.isRunning).toBe(false);
    expect(result.current.success).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it("sets success=false and error on complete event with success=false", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    act(() => {
      result.current.execute();
    });

    act(() => {
      lastEventSource!._dispatchMessage({
        type: "complete",
        line: "",
        progress: 0,
        success: false,
        error: "SFC scan failed with exit code 1",
      });
    });

    expect(result.current.isRunning).toBe(false);
    expect(result.current.success).toBe(false);
    expect(result.current.error).toBe("SFC scan failed with exit code 1");
  });

  it("sets error='Connection lost' on EventSource error", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    act(() => {
      result.current.execute();
    });

    act(() => {
      lastEventSource!._dispatchError();
    });

    expect(result.current.isRunning).toBe(false);
    expect(result.current.success).toBe(false);
    expect(result.current.error).toBe("Connection lost");
  });

  it("stop() closes EventSource and sets isRunning=false", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    act(() => {
      result.current.execute();
    });

    const es = lastEventSource!;

    act(() => {
      result.current.stop();
    });

    expect(result.current.isRunning).toBe(false);
    expect(es.close).toHaveBeenCalled();
  });

  it("reset() clears all state", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    act(() => {
      result.current.execute();
    });

    act(() => {
      lastEventSource!._dispatchMessage({
        type: "output",
        line: "Some output",
        progress: 0,
        success: false,
        error: "",
      });
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.isRunning).toBe(false);
    expect(result.current.output).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(result.current.success).toBeNull();
  });

  it("re-execute resets output and opens a fresh EventSource", () => {
    const { result } = renderHook(() => useActionStream("maintenance:sfc"));

    act(() => {
      result.current.execute();
    });

    act(() => {
      lastEventSource!._dispatchMessage({
        type: "output",
        line: "Old output",
        progress: 0,
        success: false,
        error: "",
      });
    });

    const firstEs = lastEventSource;

    act(() => {
      result.current.execute();
    });

    expect(firstEs?.close).toHaveBeenCalled();
    expect(result.current.output).toEqual([]);
    expect(result.current.isRunning).toBe(true);
  });

  it("closes the stream when the component goes away mid-action", () => {
    // An unmounted component cannot press stop. DISM runs for minutes and the
    // user switches tabs; without an unmount cleanup the browser holds the
    // connection open and keeps reconnecting to it, once per action started.
    const { result, unmount } = renderHook(() =>
      useActionStream("maintenance:dism"),
    );

    act(() => {
      result.current.execute();
    });
    const es = lastEventSource;
    expect(es?.close).not.toHaveBeenCalled();

    unmount();

    expect(es?.close).toHaveBeenCalled();
  });
});
