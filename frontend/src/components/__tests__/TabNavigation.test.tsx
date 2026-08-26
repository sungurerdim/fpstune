/**
 * `role="tab"` is a promise, and the strip made it without keeping it.
 *
 * Six buttons carried `role="tab"` and `aria-selected` and nothing else: no
 * `aria-controls`, no roving `tabIndex`, no Arrow handler. Assistive technology
 * therefore announced "tab 1 of 6" and offered arrow-key navigation that did
 * nothing, which is strictly worse than six plain buttons would have been — a
 * plain button at least behaves the way it is announced.
 *
 * These pin the APG contract that closes the gap. Keyboard events are fired
 * directly rather than driven through `userEvent`, because what is under test
 * is the key handler, not the typing.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "../../test/utils";
import { TabNavigation } from "../TabNavigation";
import { useStore } from "../../store";

// The activity drawer polls and is not what these are about.
vi.mock("../ActivityLog", () => ({ ActivityLog: () => null }));

function tabButtons() {
  return screen.getAllByRole("tab");
}

describe("TabNavigation keeps the keyboard contract its roles promise", () => {
  beforeEach(() => {
    useStore.setState({
      activeTab: "home",
      settings: new Map(),
    } as never);
  });

  it("exposes exactly one tab strip over the six tabs", () => {
    render(<TabNavigation />);

    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(tabButtons()).toHaveLength(6);
  });

  it("keeps every tab findable by the words on it, at any width", () => {
    // The label used to be `hidden md:inline`, which is display:none — below
    // md the tab had no accessible name at all, only an icon.
    render(<TabNavigation />);

    expect(
      screen.getByRole("tab", { name: /Software Tweaks/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Home/ })).toBeInTheDocument();
  });

  it("puts only the selected tab in the page's tab order", () => {
    render(<TabNavigation />);

    const [home, ...rest] = tabButtons();
    expect(home).toHaveAttribute("aria-selected", "true");
    expect(home).toHaveAttribute("tabindex", "0");
    for (const tab of rest) {
      expect(tab).toHaveAttribute("tabindex", "-1");
    }
  });

  it("moves selection and focus one tab right on ArrowRight", () => {
    render(<TabNavigation />);
    const tabs = tabButtons();

    tabs[0].focus();
    fireEvent.keyDown(tabs[0], { key: "ArrowRight" });

    expect(tabButtons()[1]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabButtons()[1]);
  });

  it("wraps ArrowLeft from the first tab round to the last", () => {
    render(<TabNavigation />);
    const tabs = tabButtons();

    tabs[0].focus();
    fireEvent.keyDown(tabs[0], { key: "ArrowLeft" });

    const last = tabButtons()[5];
    expect(last).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(last);
  });

  it("jumps to the ends on Home and End", () => {
    render(<TabNavigation />);

    fireEvent.keyDown(tabButtons()[0], { key: "End" });
    expect(tabButtons()[5]).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(tabButtons()[5], { key: "Home" });
    expect(tabButtons()[0]).toHaveAttribute("aria-selected", "true");
  });

  it("leaves other keys to the browser", () => {
    render(<TabNavigation />);

    fireEvent.keyDown(tabButtons()[0], { key: "ArrowDown" });

    expect(tabButtons()[0]).toHaveAttribute("aria-selected", "true");
  });

  it("names a panel only from the tab that actually has one", () => {
    // Only the selected panel is rendered, so `aria-controls` on the other five
    // could only point at an id that is not in the document.
    render(<TabNavigation />);

    const [selected, ...rest] = tabButtons();
    expect(selected).toHaveAttribute("aria-controls");
    for (const tab of rest) {
      expect(tab).not.toHaveAttribute("aria-controls");
    }
  });
});
