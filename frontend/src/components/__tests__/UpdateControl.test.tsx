/**
 * The update control reaches the network only when pressed, and offers an
 * install only for a release the backend says it can verify.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "../../test/utils";
import { UpdateControl } from "../UpdateControl";
import { updateApi } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  updateApi: { check: vi.fn(), install: vi.fn() },
}));

describe("UpdateControl", () => {
  beforeEach(() => {
    vi.mocked(updateApi.check).mockReset();
    vi.mocked(updateApi.install).mockReset();
  });

  it("asks nothing until it is pressed", () => {
    render(<UpdateControl />);
    expect(updateApi.check).not.toHaveBeenCalled();
  });

  it("offers the install only when the release can be verified", async () => {
    vi.mocked(updateApi.check).mockResolvedValue({
      current: "0.1.0",
      latest: "0.2.0",
      update_available: true,
      can_install: true,
      url: "https://github.com/sungurerdim/fpstune/releases",
      error: null,
    });
    vi.mocked(updateApi.install).mockResolvedValue({ installed: true, message: "done" });

    render(<UpdateControl />);
    fireEvent.click(screen.getByRole("button", { name: /check for updates/i }));

    const install = await screen.findByRole("button", { name: /update to 0\.2\.0/i });
    fireEvent.click(install);
    await waitFor(() => expect(updateApi.install).toHaveBeenCalledOnce());
  });

  it("does not offer an install the backend cannot verify", async () => {
    vi.mocked(updateApi.check).mockResolvedValue({
      current: "0.1.0",
      latest: "0.2.0",
      update_available: true,
      can_install: false,
      url: "https://github.com/sungurerdim/fpstune/releases",
      error: null,
    });

    render(<UpdateControl />);
    fireEvent.click(screen.getByRole("button", { name: /check for updates/i }));

    await waitFor(() => expect(updateApi.check).toHaveBeenCalledOnce());
    expect(screen.queryByRole("button", { name: /update to/i })).toBeNull();
  });
});
