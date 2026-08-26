/**
 * A tab strip with no panel to point at.
 *
 * `TabNavigation` declared `role="tablist"` and `role="tab"`; `App.tsx` had no
 * `role` and no `aria-` attribute anywhere, so the six tabs governed nothing a
 * screen reader could find. The association has to be asserted from both ends at
 * once — the ids are built in two different files, and a prefix that drifts in
 * one of them breaks the link without moving a pixel.
 *
 * The panels themselves are stubbed: what is under test is the wiring around
 * them, and the real ones each open a detection pipeline.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "../../test/utils";
import App from "../../App";
import { useStore } from "../../store";

vi.mock("../ActivityLog", () => ({ ActivityLog: () => null }));
vi.mock("../CleanupRunnerProvider", () => ({
  CleanupRunnerProvider: () => null,
}));
vi.mock("../HomeTab", () => ({ HomeTab: () => <p>home panel</p> }));
vi.mock("../SettingsTab", () => ({ SettingsTab: () => <p>software panel</p> }));
vi.mock("../DiskCleanupTab", () => ({ DiskCleanupTab: () => <p>cleanup panel</p> }));
vi.mock("../HardwareTab", () => ({ HardwareTab: () => <p>hardware panel</p> }));
vi.mock("../GameTweaksTab", () => ({ GameTweaksTab: () => <p>games panel</p> }));
vi.mock("../BenchmarksTab", () => ({ BenchmarksTab: () => <p>benchmarks panel</p> }));

function assertTabOwnsThePanel() {
  const selected = screen.getByRole("tab", { selected: true });
  const panel = screen.getByRole("tabpanel");

  expect(selected.getAttribute("aria-controls")).toBe(panel.id);
  expect(panel.getAttribute("aria-labelledby")).toBe(selected.id);
  expect(panel.id).toBeTruthy();
  expect(selected.id).toBeTruthy();
}

describe("the selected tab and the panel on screen are one thing", () => {
  beforeEach(() => {
    useStore.setState({ activeTab: "home", settings: new Map() } as never);
  });

  it("ties the panel to the tab that selected it", () => {
    render(<App />);

    expect(screen.getByText("home panel")).toBeInTheDocument();
    assertTabOwnsThePanel();
  });

  it("keeps the tie after the tab changes", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("tab", { name: /Game Tweaks/ }));

    expect(screen.getByText("games panel")).toBeInTheDocument();
    assertTabOwnsThePanel();
  });

  it("keeps the tie when the arrow keys move the selection", () => {
    render(<App />);

    const home = screen.getByRole("tab", { selected: true });
    home.focus();
    fireEvent.keyDown(home, { key: "End" });

    expect(screen.getByText("benchmarks panel")).toBeInTheDocument();
    assertTabOwnsThePanel();
  });

  it("shows exactly one panel at a time", () => {
    render(<App />);

    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
  });
});
