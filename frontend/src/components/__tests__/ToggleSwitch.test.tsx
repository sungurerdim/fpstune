/**
 * The one on/off primitive nearly every surface renders — tweak rows, audio
 * devices, network adapters — asserted here at the source so each call site
 * inherits the guarantees instead of re-proving them.
 *
 * The defect this file exists to keep out shipped: the control was a
 * `<button>` with no content, no role and no state, so a screen reader
 * announced "button" — not what it was, not what it controlled, not whether it
 * was on. On screen it looked perfect, which is exactly how it survived.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToggleSwitch } from "../ui/ToggleSwitch";

describe("a screen reader hears a switch with a name and a state", () => {
  it("announces role switch, named by the caller's title, not an unnamed button", () => {
    render(
      <ToggleSwitch enabled={false} onToggle={() => {}} title="Loudness EQ" />,
    );

    // Queried by role AND accessible name: `getByRole("button")` would still
    // pass on the version that said nothing about itself.
    expect(
      screen.getByRole("switch", { name: "Loudness EQ" }),
    ).toBeInTheDocument();
  });

  it("carries on/off in aria-checked, so the state never travels by colour alone", () => {
    const { rerender } = render(
      <ToggleSwitch enabled={false} onToggle={() => {}} title="Loudness EQ" />,
    );

    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");

    rerender(
      <ToggleSwitch enabled={true} onToggle={() => {}} title="Loudness EQ" />,
    );

    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
  });

  it("keeps role and state even when the caller passes no title", () => {
    // The tweak rows currently pass no title at all; the switch must still be
    // a switch with a state there, not fall back to an anonymous button.
    render(<ToggleSwitch enabled={true} onToggle={() => {}} />);

    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
  });
});

describe("the switch works without a pointer", () => {
  it("activates with Space from the keyboard", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(
      <ToggleSwitch enabled={false} onToggle={onToggle} title="Loudness EQ" />,
    );

    await user.tab();
    expect(screen.getByRole("switch")).toHaveFocus();

    await user.keyboard(" ");
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("activates with Enter from the keyboard", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(
      <ToggleSwitch enabled={false} onToggle={onToggle} title="Loudness EQ" />,
    );

    await user.tab();
    await user.keyboard("{Enter}");

    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});

describe("a disabled switch is inert, not merely faded", () => {
  it("reports disabled and ignores clicks", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(
      <ToggleSwitch
        enabled={false}
        onToggle={onToggle}
        disabled
        title="Cannot control this adapter"
      />,
    );

    const toggle = screen.getByRole("switch");
    expect(toggle).toBeDisabled();

    await user.click(toggle);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("carries the reason it is inert as its own description, not as adjacent text", () => {
    // The reason shipped as a badge next to the switch: correct on screen,
    // unreachable in sequence — a screen-reader user lands on the switch,
    // hears it is disabled, and only learns why one stop later.
    render(
      <>
        <ToggleSwitch
          enabled={false}
          onToggle={() => {}}
          disabled
          title="Ethernet"
          describedBy="why-inert"
        />
        <span id="why-inert">Not controllable</span>
      </>,
    );

    const toggle = screen.getByRole("switch", { name: "Ethernet" });
    expect(toggle).toHaveAttribute("aria-describedby", "why-inert");
    expect(
      document.getElementById(
        toggle.getAttribute("aria-describedby") as string,
      ),
    ).toHaveTextContent("Not controllable");
  });

  it("is skipped by Tab, so the keyboard cannot fire what the mouse cannot", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(
      <ToggleSwitch
        enabled={false}
        onToggle={onToggle}
        disabled
        title="Cannot control this adapter"
      />,
    );

    await user.tab();
    expect(screen.getByRole("switch")).not.toHaveFocus();

    await user.keyboard(" {Enter}");
    expect(onToggle).not.toHaveBeenCalled();
  });
});

describe("no half-working control mid-operation", () => {
  it("leaves the tree entirely while pending, so a second press cannot double-fire", () => {
    render(
      <ToggleSwitch
        enabled={false}
        onToggle={() => {}}
        isPending
        title="Loudness EQ"
      />,
    );

    expect(screen.queryByRole("switch")).toBeNull();
    expect(
      screen.getByRole("status", { name: "Loudness EQ" }),
    ).toBeInTheDocument();
  });
});
