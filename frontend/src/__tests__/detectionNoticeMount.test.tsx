/**
 * One detection notice, mounted at app level.
 *
 * The notice used to be mounted by Home, Settings and Games with a different
 * `owns` filter each, so the same failed setting was reported on one tab and
 * silently absent on another (Hardware, Cleanup and Benchmarks had no notice at
 * all). Two guards: the source holds exactly one mount, and a failure raised
 * while the user is on a tab that never mounted one is still on screen — and
 * stays on screen, once, across tab changes.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "../test/utils";
import App from "../App";
import { useStore } from "../store";
import type { Setting } from "../types/setting";

vi.mock("../components/ActivityLog", () => ({ ActivityLog: () => null }));
vi.mock("../components/FirstRunNotice", () => ({ FirstRunNotice: () => null }));
vi.mock("../components/OsUpdateNotice", () => ({ OsUpdateNotice: () => null }));
vi.mock("../components/SelfCheckNotice", () => ({ SelfCheckNotice: () => null }));
vi.mock("../components/CleanupRunnerProvider", () => ({
  CleanupRunnerProvider: () => null,
}));
vi.mock("../components/OptimizeTab", () => ({ OptimizeTab: () => <p>optimize panel</p> }));
vi.mock("../components/DiskCleanupTab", () => ({ DiskCleanupTab: () => <p>cleanup panel</p> }));
vi.mock("../components/BenchmarksTab", () => ({ BenchmarksTab: () => <p>benchmarks panel</p> }));

const SOURCES = import.meta.glob("../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const FAILED = {
  id: "network:receive_buffers",
  module: "network",
  name: "receive_buffers",
  displayName: "Receive Buffers",
  isApplicable: true,
  currentValue: "enabled",
  detectionError: "Detection timed out",
} as unknown as Setting;

describe("DetectionNotice mount", () => {
  it("is mounted exactly once in shipped source, and by App", () => {
    const mounts = Object.entries(SOURCES)
      .filter(([path]) => !path.includes(".test.") && !path.includes("__tests__/"))
      .filter(([, source]) => source.includes("<DetectionNotice"))
      .map(([path]) => path);
    expect(mounts).toEqual(["../App.tsx"]);
  });

  describe("at app level", () => {
    beforeEach(() => {
      useStore.setState({
        activeTab: "measure",
        settings: new Map([[FAILED.id, FAILED]]),
      } as never);
    });

    it("reports a failure on a tab that never mounted a notice of its own", () => {
      render(<App />);
      expect(screen.getByText(/1 setting could not be checked/)).toBeInTheDocument();
    });

    it("keeps one notice, not one per tab, when the tab changes", () => {
      render(<App />);
      fireEvent.click(screen.getByRole("tab", { name: /Optimize/ }));
      expect(screen.getAllByText(/1 setting could not be checked/)).toHaveLength(1);
    });
  });
});
