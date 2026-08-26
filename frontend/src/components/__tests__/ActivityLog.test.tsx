/**
 * Tests for ActivityLog component.
 * Tests button state, panel open/close, loading state, and entry rendering.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ActivityLog } from "../ActivityLog";
import { server } from "../../test/mocks/server";

function makeWrapper(queryClient?: QueryClient) {
  const qc =
    queryClient ??
    new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { Wrapper, queryClient: qc };
}

describe("ActivityLog", () => {
  beforeEach(() => {
    server.use(
      http.get("/api/activity", () =>
        HttpResponse.json({
          entries: [
            {
              timestamp: "12:01:02",
              message: "Applied timer:hpet successfully",
              level: "success",
            },
            {
              timestamp: "12:01:05",
              message: "Failed to apply power:usb",
              level: "error",
            },
          ],
        }),
      ),
    );
  });

  // Helper: find the open-activity-log button by its title attribute
  function getOpenButton() {
    return screen.getByTitle("Open activity log");
  }

  it("renders an Activity button", () => {
    const { Wrapper } = makeWrapper();
    render(<ActivityLog />, { wrapper: Wrapper });
    expect(getOpenButton()).toBeInTheDocument();
  });

  it("does not show the panel by default (panel is closed)", () => {
    const { Wrapper } = makeWrapper();
    render(<ActivityLog />, { wrapper: Wrapper });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens the panel when the Activity button is clicked", async () => {
    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<ActivityLog />, { wrapper: Wrapper });

    await user.click(getOpenButton());

    expect(screen.getByRole("dialog", { name: /activity log/i })).toBeInTheDocument();
  });

  it("shows 'Activity Log' heading inside the panel", async () => {
    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<ActivityLog />, { wrapper: Wrapper });

    await user.click(getOpenButton());

    expect(screen.getByRole("heading", { name: /activity log/i })).toBeInTheDocument();
  });

  it("closes panel when Close button is clicked", async () => {
    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<ActivityLog />, { wrapper: Wrapper });

    await user.click(getOpenButton());
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /close activity log/i }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes panel when Escape key is pressed", async () => {
    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<ActivityLog />, { wrapper: Wrapper });

    await user.click(getOpenButton());
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders log entries from API after panel opens", async () => {
    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<ActivityLog />, { wrapper: Wrapper });

    await user.click(getOpenButton());

    await waitFor(() => {
      expect(
        screen.getByText("Applied timer:hpet successfully"),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("Failed to apply power:usb")).toBeInTheDocument();
  });

  it("shows timestamps for log entries", async () => {
    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<ActivityLog />, { wrapper: Wrapper });

    await user.click(getOpenButton());

    await waitFor(() => {
      expect(screen.getByText("12:01:02")).toBeInTheDocument();
    });
  });

  it("shows an error dot on the button when entries contain errors", async () => {
    // error entry is in the default handler
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    // Pre-populate cache so the dot appears without opening the panel
    await qc.prefetchQuery({
      queryKey: ["activity"],
      queryFn: () =>
        fetch("/api/activity?limit=20").then((r) => r.json()) as Promise<{
          entries: { timestamp: string; message: string; level: string }[];
        }>,
    });

    const { Wrapper } = makeWrapper(qc);
    render(<ActivityLog />, { wrapper: Wrapper });

    await waitFor(() => {
      // Error dot is a span with rounded-full bg-destructive — aria-hidden=true
      const dot = document.querySelector(
        '[aria-hidden="true"].bg-destructive.rounded-full',
      );
      expect(dot).not.toBeNull();
    });
  });

  it("shows 'No recent activity' when entries list is empty", async () => {
    server.use(
      http.get("/api/activity", () =>
        HttpResponse.json({ entries: [] }),
      ),
    );

    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<ActivityLog />, { wrapper: Wrapper });

    await user.click(screen.getByTitle("Open activity log"));

    await waitFor(() => {
      expect(screen.getByText("No recent activity")).toBeInTheDocument();
    });
  });
});
