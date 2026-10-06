/**
 * The history page on a phone-width window.
 *
 * Two defects shared one cause and are pinned together: the selection toolbar
 * ran off the right edge (the page grew to 459px, 517px in Turkish) because its
 * slot was sized to its widest line, and a long setting name was clipped by
 * `truncate` with no way to read the rest. jsdom measures nothing, so these pin
 * the classes that make the browser behave, not the pixels.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "../../test/utils";
import { HistoryTab } from "../HistoryTab";
import type { HistoryResponse } from "../../lib/api";

vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({ run: vi.fn(), stop: vi.fn(), isRunning: false }),
}));

const history: HistoryResponse = {
  settings: [
    {
      setting_id: "network:nagle_algorithm",
      last_action: "apply",
      value: "disabled",
      at: 1_759_650_000,
    },
  ],
  entries: [],
};

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, historyApi: { get: () => Promise.resolve(history) } };
});

describe("HistoryTab at a narrow width", () => {
  it("lets the selection toolbar wrap inside the header's own width", async () => {
    render(<HistoryTab />);

    const selectAll = await screen.findByRole("button", { name: "Select all" });
    const toolbar = selectAll.parentElement as HTMLElement;
    expect(toolbar).toHaveClass("flex-wrap");
    // The slot holding it is capped at the header's width; uncapped, `shrink-0`
    // sized it to the unwrapped toolbar and the toolbar never had a reason to wrap.
    const slot = toolbar.closest("[data-slot='scope-actions']") as HTMLElement;
    expect(slot).toHaveClass("max-w-full");
  });

  it("names a clipped row in full on hover", async () => {
    render(<HistoryTab />);

    const name = await screen.findByText("network:nagle_algorithm");
    expect(name).toHaveClass("truncate");
    expect(name).toHaveAttribute("title", "network:nagle_algorithm");
  });
});
