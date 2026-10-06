/**
 * The history page: what fpstune changed this session, and the one way back.
 *
 * Guards that every row offers Reset to default and nothing else — no earlier
 * value is shown or restored, because fpstune keeps none — and that a row whose
 * setting is known names the default it writes by domain.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, metricChip, render, screen, waitFor, within } from "../../test/utils";
import { HistoryTab } from "../HistoryTab";
import { useStore } from "../../store";
import type { HistoryResponse } from "../../lib/api";

const run = vi.fn();

vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({ run, stop: vi.fn(), isRunning: false }),
}));

const history: HistoryResponse = {
  settings: [
    {
      setting_id: "network:nagle_algorithm",
      last_action: "apply",
      value: "disabled",
      at: 1_759_650_000,
    },
    {
      setting_id: "system:game_mode",
      last_action: "apply",
      value: "enabled",
      at: 1_759_640_000,
    },
    {
      setting_id: "power:hibernation",
      last_action: "revert",
      value: "on",
      at: 1_759_630_000,
    },
  ],
  entries: [],
};

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, historyApi: { get: () => Promise.resolve(history) } };
});

beforeEach(() => {
  run.mockReset();
  useStore.setState({ settings: new Map() } as never);
});

describe("HistoryTab", () => {
  it("splits what is still changed from what was already put back", async () => {
    render(<HistoryTab />);
    const active = await screen.findByRole("heading", { name: "Still changed by fpstune" });
    const reverted = screen.getByRole("heading", { name: "Already put back" });
    // The count is its own chip beside the title, not text run into it.
    expect(metricChip("2 settings", active.closest("section")!)).toBeInTheDocument();
    expect(metricChip("1 settings", reverted.closest("section")!)).toBeInTheDocument();
    // The row says what happened to it, and nothing about an earlier value.
    expect(screen.getByText(/Reverted/)).toBeInTheDocument();
    expect(screen.queryByText(/before/)).not.toBeInTheDocument();
  });

  it("gives each row exactly one way back: Reset to default", async () => {
    render(<HistoryTab />);
    const reset = await screen.findByRole("button", {
      name: "Reset network:nagle_algorithm to its default",
    });
    const row = reset.closest("li") as HTMLElement;
    expect(within(row).getAllByRole("button")).toEqual([reset]);
    expect(reset).toHaveTextContent("Reset to default");
  });

  it("resets one row to its default", async () => {
    render(<HistoryTab />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Reset network:nagle_algorithm to its default",
      }),
    );
    expect(run).toHaveBeenCalledWith("reset", ["network:nagle_algorithm"]);
  });

  it("names the default a row's reset writes, by the setting's domain", async () => {
    useStore.setState({
      settings: new Map([
        [
          "system:game_mode",
          { id: "system:game_mode", name: "game_mode", displayName: "Game Mode", domain: "software" },
        ],
      ]),
    } as never);
    render(<HistoryTab />);
    const reset = await screen.findByRole("button", {
      name: "Reset Game Mode to its default",
    });
    expect(reset).toHaveAttribute("title", "Windows default");
  });

  it("bulk reset takes every selected row", async () => {
    render(<HistoryTab />);
    fireEvent.click(await screen.findByRole("button", { name: "Select all" }));
    fireEvent.click(screen.getByRole("button", { name: /Reset selected to default \(2\)/ }));
    await waitFor(() =>
      expect(run).toHaveBeenLastCalledWith("reset", [
        "network:nagle_algorithm",
        "system:game_mode",
      ]),
    );
  });
});
