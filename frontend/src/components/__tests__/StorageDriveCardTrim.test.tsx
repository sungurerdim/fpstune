/**
 * A TRIM state the backend could not read is shown as unknown, never as "off".
 *
 * The backend used to answer `false` both for "TRIM is disabled" and for "the
 * fsutil text could not be parsed" — and on a non-English Windows the second was
 * the common case, so every SSD carried a warning nothing had measured. The
 * field is tri-state now; the card must render all three states differently.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "../../test/utils";
import { StorageDriveCard } from "../hardware/StorageDriveCard";
import type { StorageDriveInfo } from "../../lib/api";

vi.mock("../../lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  api: {
    optimizeDrive: vi.fn().mockResolvedValue({ success: true, message: "ok" }),
  },
}));

function ssd(trim: boolean | null): StorageDriveInfo {
  return {
    drive_letter: "C",
    model: "Samsung SSD 990 PRO 1TB",
    media_type: "SSD",
    size_gb: 931,
    free_gb: 412,
    trim_enabled: trim,
    bus_type: "NVMe",
  };
}

describe("TRIM state on the storage card", () => {
  it("renders an unknown state as unknown, with the reason readable", () => {
    render(<StorageDriveCard drive={ssd(null)} />);
    expect(
      screen.getByRole("img", { name: /could not be read/i }),
    ).toBeInTheDocument();
  });

  it("renders a known-on state without the unknown marker", () => {
    render(<StorageDriveCard drive={ssd(true)} />);
    expect(
      screen.queryByRole("img", { name: /could not be read/i }),
    ).toBeNull();
  });

  it("renders a known-off state without the unknown marker", () => {
    render(<StorageDriveCard drive={ssd(false)} />);
    expect(
      screen.queryByRole("img", { name: /could not be read/i }),
    ).toBeNull();
  });

  it("says nothing about TRIM for a drive that is not an SSD", () => {
    render(<StorageDriveCard drive={{ ...ssd(null), media_type: "HDD" }} />);
    expect(screen.queryByText(/TRIM/)).toBeNull();
  });
});
