/**
 * Any display mode fpstune writes is asked about once, and kept only on a yes.
 *
 * The mode reverts on its own unless kept, which is what turns a mode the panel
 * cannot show into a fifteen-second black screen instead of a permanent one.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "../../test/utils";
import { DisplayModeConfirm } from "../DisplayModeConfirm";
import { api } from "../../lib/api";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getPendingDisplayChanges: vi.fn(),
      keepAllDisplayChanges: vi.fn().mockResolvedValue({ success: true, message: "" }),
    },
  };
});

const pending = vi.mocked(api.getPendingDisplayChanges);
const keepAll = vi.mocked(api.keepAllDisplayChanges);

beforeEach(() => {
  pending.mockReset();
  keepAll.mockClear();
});

describe("DisplayModeConfirm", () => {
  it("asks with the backend's own time left and keeps every pending display on yes", async () => {
    pending.mockResolvedValue({ devices: ["\\\\.\\DISPLAY1", "\\\\.\\DISPLAY2"], seconds_left: 12 });
    render(<DisplayModeConfirm />);

    expect(await screen.findByText("Keep the new display mode?")).toBeInTheDocument();
    expect(screen.getByText(/2 monitor\(s\).*12 s/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Keep" }));
    await waitFor(() => expect(keepAll).toHaveBeenCalledTimes(1));
  });

  it("does not keep anything on no, so the timer puts the old mode back", async () => {
    pending.mockResolvedValue({ devices: ["\\\\.\\DISPLAY1"], seconds_left: 9 });
    render(<DisplayModeConfirm />);

    fireEvent.click(await screen.findByRole("button", { name: "Don't keep" }));

    await waitFor(() =>
      expect(screen.queryByText("Keep the new display mode?")).not.toBeInTheDocument(),
    );
    expect(keepAll).not.toHaveBeenCalled();
  });

  it("stays closed when nothing is waiting", async () => {
    pending.mockResolvedValue({ devices: [], seconds_left: 0 });
    render(<DisplayModeConfirm />);
    await waitFor(() => expect(pending).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
