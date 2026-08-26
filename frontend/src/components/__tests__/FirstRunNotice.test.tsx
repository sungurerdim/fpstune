/**
 * E6: the welcome shows exactly once.
 *
 * The defect: a first-time user's first available action was a bulk registry
 * write behind a bare button, with nothing saying the app had not touched
 * anything yet. The notice must appear on a fresh machine, say so, explain
 * the Administrator shield — and never reappear once dismissed.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { FirstRunNotice } from "../FirstRunNotice";

// This jsdom's localStorage is partial; a real Map-backed stub makes the
// persistence observable.
function stubStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
  });
}

describe("FirstRunNotice", () => {
  beforeEach(() => {
    stubStorage();
  });

  it("shows on first run: nothing changed yet, and what Admin means", () => {
    render(<FirstRunNotice />);
    expect(screen.getByText(/Nothing has been changed yet/)).toBeInTheDocument();
    expect(screen.getByText(/Administrator/)).toBeInTheDocument();
  });

  it("does not show on the second run", () => {
    const first = render(<FirstRunNotice />);
    fireEvent.click(screen.getByRole("button", { name: /Got it/ }));
    expect(
      screen.queryByText(/Nothing has been changed yet/),
    ).not.toBeInTheDocument();
    first.unmount();

    // A fresh mount is the second launch.
    render(<FirstRunNotice />);
    expect(
      screen.queryByText(/Nothing has been changed yet/),
    ).not.toBeInTheDocument();
  });
});
