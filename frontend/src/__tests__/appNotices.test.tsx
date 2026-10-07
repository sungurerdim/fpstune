/**
 * What is true of the app, or of the whole machine, is said once, above whichever
 * tab is open.
 *
 * The welcome, the "Windows was updated" note and the detection self-check used
 * to live on Home alone: a user who opened the app on any other tab never read
 * them, and a user who never opened Home was never welcomed. Two guards: each is
 * mounted once in shipped source, by App, and each is on screen on a tab that
 * has nothing to do with it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "../test/utils";
import App from "../App";
import { useStore } from "../store";
import { api } from "../lib/api";

vi.mock("../components/ActivityLog", () => ({ ActivityLog: () => null }));
vi.mock("../components/CleanupRunnerProvider", () => ({
  CleanupRunnerProvider: () => null,
}));
vi.mock("../components/SelfCheckNotice", () => ({ SelfCheckNotice: () => <p>self-check notice</p> }));
vi.mock("../components/OptimizeTab", () => ({ OptimizeTab: () => <p>optimize panel</p> }));
vi.mock("../components/DiskCleanupTab", () => ({ DiskCleanupTab: () => <p>cleanup panel</p> }));
vi.mock("../components/HardwareTab", () => ({ HardwareTab: () => <p>hardware panel</p> }));
vi.mock("../components/BenchmarksTab", () => ({ BenchmarksTab: () => <p>benchmarks panel</p> }));

const SOURCES = import.meta.glob("../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// This jsdom's localStorage is partial; a real Map-backed stub makes the
// dismissal observable.
function stubStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
  });
}

describe("app-level notices", () => {
  it("are each mounted exactly once in shipped source, and by App", () => {
    for (const notice of ["FirstRunNotice", "OsUpdateNotice", "SelfCheckNotice"]) {
      const mounts = Object.entries(SOURCES)
        .filter(([path]) => !path.includes(".test.") && !path.includes("__tests__/"))
        .filter(([, source]) => source.includes(`<${notice}`))
        .map(([path]) => path);
      expect(mounts, notice).toEqual(["../App.tsx"]);
    }
  });

  describe("on a tab that has nothing to do with them", () => {
    beforeEach(() => {
      vi.restoreAllMocks();
      stubStorage();
      vi.spyOn(api, "getOsBuildChange").mockResolvedValue({
        previous: "26100.4061",
        current: "26200.6584",
        changed: true,
      });
      useStore.setState({ activeTab: "benchmarks", settings: new Map() } as never);
    });

    it("welcomes a first run, and does not again once dismissed", () => {
      render(<App />);
      expect(screen.getByText(/Nothing has been changed yet/)).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /Got it/ }));
      fireEvent.click(screen.getByRole("tab", { name: /Optimize/ }));

      expect(screen.queryByText(/Nothing has been changed yet/)).not.toBeInTheDocument();
    });

    it("says Windows was updated, once, across tab changes", async () => {
      render(<App />);

      expect(await screen.findByText(/26100\.4061 → 26200\.6584/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("tab", { name: /Cleanup/ }));
      expect(screen.getAllByText(/26100\.4061 → 26200\.6584/)).toHaveLength(1);
    });

    it("shows the detection self-check", () => {
      render(<App />);

      expect(screen.getByText("self-check notice")).toBeInTheDocument();
    });
  });
});
