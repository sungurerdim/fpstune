/**
 * Vitest test setup file.
 * Configures testing environment and global mocks.
 */

import "@testing-library/jest-dom";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, beforeAll, afterAll, vi } from "vitest";
import { server } from "./mocks/server";

// findBy*/waitFor give up after 1 s by default. The pre-push gate runs vitest
// beside an eight-worker pytest, and on that loaded machine a render that
// settles in 100 ms alone took longer: "Unable to find role=button" with the
// button on its way. Patience only — every assertion is unchanged.
configure({ asyncUtilTimeout: 5000 });

// Setup MSW server
beforeAll(() => {
  server.listen({ onUnhandledRequest: "warn" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => {
  server.close();
  // A log that lands after this file's last test belongs to no test: a query's
  // retry or refetch finishing late on a loaded machine. Reaching the console
  // then raced the worker's teardown and failed the whole run with
  // "Closing rpc while onUserConsoleLog was pending" (1 run in 3, seen in
  // HomeAdvisories.test.tsx). Every test has finished by now, so nothing a test
  // could assert on is lost.
  for (const method of ["log", "info", "warn", "error", "debug"] as const) {
    vi.spyOn(console, method).mockImplementation(() => undefined);
  }
});

// Mock window.matchMedia for components that use it
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver
class ResizeObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

window.ResizeObserver = ResizeObserverMock;

// Mock IntersectionObserver
class IntersectionObserverMock {
  root = null;
  rootMargin = "";
  thresholds = [];

  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = vi.fn();
}

window.IntersectionObserver =
  IntersectionObserverMock as unknown as typeof IntersectionObserver;
