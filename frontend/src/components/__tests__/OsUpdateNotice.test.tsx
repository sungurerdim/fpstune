/**
 * A Windows update since the last run is said once, and only when it happened.
 *
 * Updates reset settings to Windows' own values; without this, rows a user
 * applied weeks ago show as changed with nothing saying why. A notice on a
 * first run, or when the build could not be read, would be a false alarm.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OsUpdateNotice } from "../OsUpdateNotice";
import { api, type OsBuildChange } from "../../lib/api";

function renderWith(answer: OsBuildChange) {
  vi.spyOn(api, "getOsBuildChange").mockResolvedValue(answer);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OsUpdateNotice />
    </QueryClientProvider>,
  );
}

describe("OsUpdateNotice", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("names both builds and why the scan may show drift", async () => {
    renderWith({ previous: "26100.4061", current: "26200.6584", changed: true });

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent("26100.4061 → 26200.6584");
    expect(notice).toHaveTextContent(/put settings back to Windows' own values/);
  });

  it("goes away when dismissed", async () => {
    renderWith({ previous: "26100.4061", current: "26200.6584", changed: true });

    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says nothing on a first run or an unchanged build", async () => {
    const spy = vi.spyOn(api, "getOsBuildChange");
    renderWith({ previous: null, current: "26100.4061", changed: false });
    await vi.waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
