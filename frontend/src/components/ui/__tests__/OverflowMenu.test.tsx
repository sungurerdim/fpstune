/**
 * The overflow menu is a real menu button, not a pointer-only popup.
 *
 * Each test names what a keyboard or screen-reader user would lose: a trigger
 * that does not announce it opens a menu, focus that stays behind the trigger,
 * an Escape that leaves the menu open or strands focus, an item that cannot be
 * reached with the arrow keys.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OverflowMenu } from "../OverflowMenu";

function items(onSelect = vi.fn()) {
  return [
    { id: "a", label: "First", onSelect },
    { id: "b", label: "Second", onSelect: vi.fn() },
    { id: "c", label: "Third", onSelect: vi.fn() },
  ];
}

describe("OverflowMenu", () => {
  it("announces itself as a menu button and starts closed", () => {
    render(<OverflowMenu label="More actions" items={items()} />);

    const trigger = screen.getByRole("button", { name: "More actions" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("opens on Enter, Space and click, and focus moves to the first item", async () => {
    const user = userEvent.setup();
    render(<OverflowMenu label="More actions" items={items()} />);
    const trigger = screen.getByRole("button", { name: "More actions" });

    trigger.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("menuitem", { name: "First" })).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(trigger).toHaveAttribute("aria-controls", screen.getByRole("menu").id);

    await user.keyboard("{Escape}");
    trigger.focus();
    await user.keyboard(" ");
    expect(screen.getByRole("menuitem", { name: "First" })).toHaveFocus();

    await user.keyboard("{Escape}");
    await user.click(trigger);
    expect(screen.getByRole("menuitem", { name: "First" })).toHaveFocus();
  });

  it("opens on ArrowUp at the last item", async () => {
    const user = userEvent.setup();
    render(<OverflowMenu label="More actions" items={items()} />);

    screen.getByRole("button", { name: "More actions" }).focus();
    await user.keyboard("{ArrowUp}");

    expect(screen.getByRole("menuitem", { name: "Third" })).toHaveFocus();
  });

  it("moves with the arrow keys, wraps, and jumps with Home and End", async () => {
    const user = userEvent.setup();
    render(<OverflowMenu label="More actions" items={items()} />);
    screen.getByRole("button", { name: "More actions" }).focus();
    await user.keyboard("{ArrowDown}");

    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Second" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("menuitem", { name: "Third" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "First" })).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("menuitem", { name: "Third" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(screen.getByRole("menuitem", { name: "First" })).toHaveFocus();
  });

  it("closes on Escape and puts focus back on the trigger", async () => {
    const user = userEvent.setup();
    render(<OverflowMenu label="More actions" items={items()} />);
    const trigger = screen.getByRole("button", { name: "More actions" });
    trigger.focus();
    await user.keyboard("{ArrowDown}");

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("closes on Tab and on a press outside", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <OverflowMenu label="More actions" items={items()} />
        <button type="button">Elsewhere</button>
      </div>,
    );
    const trigger = screen.getByRole("button", { name: "More actions" });

    await user.click(trigger);
    await user.keyboard("{Tab}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("runs the chosen item and returns focus to the trigger first", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn(() => {
      // What a confirmation dialog reads as the place to return to.
      expect(screen.getByRole("button", { name: "More actions" })).toHaveFocus();
    });
    render(<OverflowMenu label="More actions" items={items(onSelect)} />);

    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.keyboard("{Enter}");

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("keeps a disabled item reachable and announced, but inert", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <OverflowMenu
        label="More actions"
        items={[{ id: "a", label: "Windows default (0)", ariaLabel: "Already at the Windows default", disabled: true, onSelect }]}
      />,
    );

    await user.click(screen.getByRole("button", { name: "More actions" }));
    const item = screen.getByRole("menuitem", { name: "Already at the Windows default" });
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(onSelect).not.toHaveBeenCalled();
    // Still open: nothing was chosen.
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  it("draws nothing at all without items", () => {
    const { container } = render(<OverflowMenu label="More actions" items={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
