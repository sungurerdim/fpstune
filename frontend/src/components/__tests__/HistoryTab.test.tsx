/**
 * The history page: what fpstune changed, and both ways back.
 *
 * Guards the two promises C6 keeps apart — Undo writes what this machine held,
 * Windows default writes the stock value — and that a setting with no earlier
 * value on record cannot be "undone" into a reset.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "../../test/utils";
import { HistoryTab } from "../HistoryTab";
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
      can_undo: true,
      original_value: "enabled",
    },
    {
      setting_id: "system:game_mode",
      last_action: "apply",
      value: "enabled",
      at: 1_759_640_000,
      can_undo: false,
      original_value: null,
    },
    {
      setting_id: "power:hibernation",
      last_action: "undo",
      value: "on",
      at: 1_759_630_000,
      can_undo: false,
      original_value: null,
    },
  ],
  entries: [],
};

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, historyApi: { get: () => Promise.resolve(history) } };
});

beforeEach(() => run.mockReset());

describe("HistoryTab", () => {
  it("splits what is still changed from what was already put back", async () => {
    render(<HistoryTab />);
    expect(await screen.findByText(/Still changed by fpstune \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/Already put back \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/was enabled before/)).toBeInTheDocument();
  });

  it("undoes one row to what the machine held", async () => {
    render(<HistoryTab />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Undo fpstune's change to network:nagle_algorithm",
      }),
    );
    expect(run).toHaveBeenCalledWith("undo", ["network:nagle_algorithm"]);
  });

  it("offers no undo where nothing was recorded, only the Windows default", async () => {
    render(<HistoryTab />);
    const undo = await screen.findByRole("button", {
      name: "Undo fpstune's change to system:game_mode",
    });
    expect(undo).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Restore the Windows default for system:game_mode" }),
    );
    expect(run).toHaveBeenCalledWith("reset", ["system:game_mode"]);
  });

  it("bulk undo skips the rows that have no original, bulk reset takes them all", async () => {
    render(<HistoryTab />);
    fireEvent.click(await screen.findByRole("button", { name: "Select all" }));

    fireEvent.click(screen.getByRole("button", { name: /Undo selected \(1\)/ }));
    expect(run).toHaveBeenLastCalledWith("undo", ["network:nagle_algorithm"]);

    fireEvent.click(screen.getByRole("button", { name: "Select all" }));
    fireEvent.click(screen.getByRole("button", { name: /Windows default for selected \(2\)/ }));
    await waitFor(() =>
      expect(run).toHaveBeenLastCalledWith("reset", [
        "network:nagle_algorithm",
        "system:game_mode",
      ]),
    );
  });
});
