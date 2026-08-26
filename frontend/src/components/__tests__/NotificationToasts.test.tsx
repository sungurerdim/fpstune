/**
 * The store's `notifications` array had two producers and no reader.
 *
 * "Cannot reach the backend — retrying in the background." and every failed
 * cleanup operation were pushed into it, capped at fifty, and rendered by
 * nothing: a user with the backend down or a Docker prune that failed saw an
 * app that looked entirely healthy. These assert that each of those messages
 * now arrives, that it arrives without hijacking the keyboard, and that it can
 * be got rid of without a mouse.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationToasts } from "../ui/NotificationToasts";
import { useStore } from "../../store";

function raise(message: string, type: "success" | "error" | "warning" | "info") {
  act(() => {
    useStore.getState().addNotification(message, type);
  });
}

describe("a produced notification reaches the screen", () => {
  beforeEach(() => {
    useStore.setState({ notifications: [] });
  });

  it("renders the backend-unreachable message instead of swallowing it", () => {
    render(<NotificationToasts />);

    raise("Cannot reach the backend — retrying in the background.", "error");

    expect(
      screen.getByText("Cannot reach the backend — retrying in the background."),
    ).toBeInTheDocument();
  });

  it("puts an error in the assertive region and a success in the polite one", () => {
    render(<NotificationToasts />);

    raise("2 cleanup operations failed", "error");
    raise("Cleanup complete: 3 operations succeeded", "success");

    const urgent = screen.getByRole("log", { name: "Errors and warnings" });
    const routine = screen.getByRole("log", { name: "Notifications" });

    expect(urgent).toHaveAttribute("aria-live", "assertive");
    expect(routine).toHaveAttribute("aria-live", "polite");
    expect(
      within(urgent).getByText("2 cleanup operations failed"),
    ).toBeInTheDocument();
    expect(
      within(routine).getByText(/Cleanup complete/),
    ).toBeInTheDocument();
  });

  it("keeps both live regions mounted while empty, so the first message is announced", () => {
    render(<NotificationToasts />);

    // A live region created in the same tick as its first child is announced
    // unreliably or not at all — which is precisely the case that matters here,
    // because the first message of a session is usually the only one.
    expect(
      screen.getByRole("log", { name: "Errors and warnings" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("log", { name: "Notifications" }),
    ).toBeInTheDocument();
  });

  it("says which severity it is in words, not only in colour", () => {
    render(<NotificationToasts />);

    raise("2 cleanup operations failed", "error");

    expect(
      screen.getByText("Error:", { exact: false, selector: ".sr-only" }),
    ).toBeInTheDocument();
  });
});

describe("the user stays in control of the keyboard", () => {
  beforeEach(() => {
    useStore.setState({ notifications: [] });
  });

  it("does not move focus away from what the user was typing in", async () => {
    const user = userEvent.setup();
    render(
      <>
        <input aria-label="Search tweaks" />
        <NotificationToasts />
      </>,
    );

    const input = screen.getByRole("textbox", { name: "Search tweaks" });
    await user.click(input);
    expect(input).toHaveFocus();

    raise("Cannot reach the backend — retrying in the background.", "error");

    expect(input).toHaveFocus();
  });

  it("dismisses from the keyboard and drops the message from the store", async () => {
    const user = userEvent.setup();
    render(<NotificationToasts />);

    raise("Cleanup failed: Docker is not running", "error");

    await user.tab();
    const dismiss = screen.getByRole("button", {
      name: "Dismiss: Cleanup failed: Docker is not running",
    });
    expect(dismiss).toHaveFocus();

    await user.keyboard("{Enter}");

    expect(useStore.getState().notifications).toHaveLength(0);
    expect(
      screen.queryByText("Cleanup failed: Docker is not running"),
    ).toBeNull();
  });

  it("dismisses the toast the keyboard is inside when Escape is pressed", async () => {
    const user = userEvent.setup();
    render(<NotificationToasts />);

    raise("2 cleanup operations failed", "error");
    raise("Cleanup complete: 3 operations succeeded", "success");

    await user.tab();
    await user.keyboard("{Escape}");

    expect(useStore.getState().notifications.map((n) => n.message)).toEqual([
      "Cleanup complete: 3 operations succeeded",
    ]);
  });

  it("dismissing one leaves the others standing", async () => {
    const user = userEvent.setup();
    render(<NotificationToasts />);

    raise("2 cleanup operations failed", "error");
    raise("1 cleanup operation failed", "error");

    await user.click(
      screen.getByRole("button", {
        name: "Dismiss: 2 cleanup operations failed",
      }),
    );

    expect(useStore.getState().notifications.map((n) => n.message)).toEqual([
      "1 cleanup operation failed",
    ]);
  });
});
