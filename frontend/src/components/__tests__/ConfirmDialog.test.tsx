/**
 * A confirmation that can be tabbed past is not a confirmation.
 *
 * Both of this app's gates — the advanced bulk apply and the Docker/WSL
 * shutdown — shipped as a plain overlay: a fixed div with two buttons, no role,
 * no focus trap, no Escape. On screen it looks exactly like a modal. From the
 * keyboard the next Tab press leaves it for the page underneath, which is still
 * live and still announced, and the question simply never gets answered. These
 * assert the four things that make the difference, none of which are visible.
 */

import { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ConfirmDialog } from "../ui/ConfirmDialog";

function Harness({
  onConfirm = () => {},
  onCancel = () => {},
}: {
  onConfirm?: () => void;
  onCancel?: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Prune Docker
      </button>
      <ConfirmDialog
        open={open}
        title="Restart Docker & WSL?"
        confirmLabel="Prune & compact"
        onConfirm={() => {
          setOpen(false);
          onConfirm();
        }}
        onCancel={() => {
          setOpen(false);
          onCancel();
        }}
      >
        Everything will be shut down and restarted.
      </ConfirmDialog>
    </>
  );
}

function openFromTrigger() {
  const trigger = screen.getByRole("button", { name: "Prune Docker" });
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}

describe("ConfirmDialog announces itself as a dialog", () => {
  it("carries the role, the modal flag and its own title as the name", () => {
    render(<Harness />);
    openFromTrigger();

    const dialog = screen.getByRole("dialog", { name: "Restart Docker & WSL?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // The explanation is the description, not loose text the reader may or may
    // not reach before the buttons.
    const describedBy = dialog.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)).toHaveTextContent(
      "Everything will be shut down and restarted.",
    );
  });
});

describe("ConfirmDialog owns the keyboard while it is open", () => {
  it("puts initial focus on Cancel, never on the action", () => {
    render(<Harness />);
    openFromTrigger();

    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Cancel" }),
    );
  });

  it("wraps Tab from the last control back to the first", () => {
    render(<Harness />);
    openFromTrigger();

    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Prune & compact" });

    confirm.focus();
    fireEvent.keyDown(confirm, { key: "Tab" });
    expect(document.activeElement).toBe(cancel);
  });

  it("wraps Shift+Tab from the first control back to the last", () => {
    render(<Harness />);
    openFromTrigger();

    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Prune & compact" });

    cancel.focus();
    fireEvent.keyDown(cancel, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(confirm);
  });

  it("answers Escape as a cancel, not as nothing", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(<Harness onCancel={onCancel} onConfirm={onConfirm} />);
    openFromTrigger();

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("returns focus to the control that opened it", () => {
    render(<Harness />);
    const trigger = openFromTrigger();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(document.activeElement).toBe(trigger);
  });
});

describe("ConfirmDialog takes the page behind it out of reach", () => {
  it("marks every other body child inert and hidden while open", () => {
    const { baseElement } = render(<Harness />);
    openFromTrigger();

    const dialog = screen.getByRole("dialog");
    const behind = Array.from(baseElement.children).filter(
      (element) => !element.contains(dialog),
    );
    expect(behind.length).toBeGreaterThan(0);
    for (const element of behind) {
      // `inert` is what a browser honours; `aria-hidden` is what a screen
      // reader honours. The trigger sits inside this subtree, so both are
      // needed for "cannot be tabbed past" to be true of both.
      expect(element).toHaveAttribute("inert");
      expect(element).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("gives the page back when the dialog closes", () => {
    const { baseElement } = render(<Harness />);
    openFromTrigger();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    for (const element of Array.from(baseElement.children)) {
      expect(element).not.toHaveAttribute("inert");
      expect(element).not.toHaveAttribute("aria-hidden");
    }
  });
});
