/**
 * Vitest test setup file.
 * Configures testing environment and global mocks.
 */

import "@testing-library/jest-dom";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, beforeAll, afterAll, expect, vi } from "vitest";
import * as axeMatchers from "vitest-axe/matchers";
import type { AxeMatchers } from "vitest-axe";
import { server } from "./mocks/server";

// P-WCAG's rendered-tree half: the matcher the a11y tests assert with. `axe()`
// runs in each test against what actually rendered, which catches what the
// static jsx-a11y rules cannot (a wrong accessible name, a heading level skip,
// a live region nothing announces). No rule is turned off: jsdom has no layout,
// so axe itself skips the rules that need one (colour contrast above all), and
// that gap is written down in the a11y test file rather than hidden here.
expect.extend(axeMatchers);

// vitest-axe 0.1 declares its matcher against the pre-vitest-1 `Vi` namespace,
// which vitest 4 no longer has. Merging the matcher into vitest's own interfaces
// requires empty extension bodies and the original `<T = any>` signature — the
// exact shapes these rules forbid — so they are off for this augmentation only.
/* eslint-disable @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars, @typescript-eslint/no-explicit-any */
declare module "vitest" {
  interface Assertion<T = any> extends AxeMatchers {}
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}
/* eslint-enable @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars, @typescript-eslint/no-explicit-any */

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
  // "Closing rpc while onUserConsoleLog was pending" (1 run in 3, seen in a
  // test of the page since removed). Every test has finished by now, so nothing a test
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
