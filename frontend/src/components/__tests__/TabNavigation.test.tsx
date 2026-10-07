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
import { render, screen, fireEvent, within } from "../../test/utils";
import { TabNavigation } from "../TabNavigation";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

// The activity drawer polls and is not what these are about.
vi.mock("../ActivityLog", () => ({ ActivityLog: () => null }));

function tabButtons() {
  return screen.getAllByRole("tab");
}

const lastTab = (): HTMLElement => {
  const tabs = tabButtons();
  return tabs[tabs.length - 1];
};

describe("TabNavigation keeps the keyboard contract its roles promise", () => {
  beforeEach(() => {
    useStore.setState({
      activeTab: "optimize",
      settings: new Map(),
    } as never);
  });

  it("exposes exactly one tab strip over three tabs: Optimize, Cleanup, Measure, in that order", () => {
    render(<TabNavigation />);

    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(tabButtons().map((tab) => tab.getAttribute("title"))).toEqual([
      "Optimize",
      "Cleanup & Repair",
      "Measure",
    ]);
  });

  it("keeps every tab findable by the words on it, at any width", () => {
    // The label used to be `hidden md:inline`, which is display:none — below
    // md the tab had no accessible name at all, only an icon.
    render(<TabNavigation />);

    expect(screen.getByRole("tab", { name: /Optimize/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Cleanup/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Measure/ })).toBeInTheDocument();
  });

  it("puts only the selected tab in the page's tab order", () => {
    render(<TabNavigation />);

    const [first, ...rest] = tabButtons();
    expect(first).toHaveAttribute("aria-selected", "true");
    expect(first).toHaveAttribute("tabindex", "0");
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

    const last = lastTab();
    expect(last).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(last);
  });

  it("jumps to the ends on Home and End", () => {
    render(<TabNavigation />);

    fireEvent.keyDown(tabButtons()[0], { key: "End" });
    expect(lastTab()).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(lastTab(), { key: "Home" });
    expect(tabButtons()[0]).toHaveAttribute("aria-selected", "true");
  });

  it("leaves other keys to the browser", () => {
    render(<TabNavigation />);

    fireEvent.keyDown(tabButtons()[0], { key: "ArrowDown" });

    expect(tabButtons()[0]).toHaveAttribute("aria-selected", "true");
  });

  it("never wraps a tab label, and scrolls the strip instead of outgrowing it", () => {
    // The label span was `sr-only md:not-sr-only`, and `not-sr-only` resets
    // `white-space` to normal: at 768-1280px every label wrapped to 2-3 lines,
    // tabs grew from 44px to 84px and "Ölçüm" was cut mid-word. jsdom lays nothing
    // out, so what is pinned is the cause and the mechanism that replaces it.
    render(<TabNavigation />);

    const strip = screen.getByRole("tablist");
    expect(strip).toHaveClass("overflow-x-auto");
    expect(strip).toHaveClass("min-w-0");
    for (const tab of tabButtons()) {
      expect(tab).toHaveClass("whitespace-nowrap");
      // A tab squeezed below its content is how a label ends up cut.
      expect(tab).toHaveClass("shrink-0");
      const label = within(tab).getByText(tab.getAttribute("title") ?? "");
      expect(label).toHaveClass("max-lg:sr-only");
      expect(label.className).not.toContain("not-sr-only");
    }
  });

  it("gives the icon-only strip the same name on hover as for a screen reader", () => {
    render(<TabNavigation />);

    for (const tab of tabButtons()) {
      const label = tab.getAttribute("title");
      expect(label).toBeTruthy();
      expect(tab).toHaveAccessibleName(new RegExp(label as string));
    }
  });

  it("takes a row of its own until the window can hold it beside the chrome", () => {
    // Below 3xl the six labels, the brand and the update/admin/theme chrome
    // cannot share one line; the strip is `basis-full` and wraps under them.
    render(<TabNavigation />);

    const wrapper = screen.getByTestId("tab-strip");
    expect(wrapper).toHaveClass("basis-full");
    expect(wrapper).toHaveClass("min-w-0");
    expect(wrapper).toHaveClass("3xl:flex-1");
  });

  it("shows a cue at the edge that hides more tabs, and only there", () => {
    // A scroll area whose scrollbar is hidden says nothing about what lies past
    // its edge; at 390px only 135 of 304px of tabs showed with no hint of the rest.
    render(<TabNavigation />);
    const strip = screen.getByRole("tablist");

    const geometry = (scrollLeft: number) => {
      Object.defineProperty(strip, "clientWidth", { configurable: true, value: 135 });
      Object.defineProperty(strip, "scrollWidth", { configurable: true, value: 304 });
      Object.defineProperty(strip, "scrollLeft", { configurable: true, value: scrollLeft });
      fireEvent.scroll(strip);
    };

    // Everything fits (jsdom measures 0 everywhere): no cue.
    expect(screen.queryByTestId("tab-strip-more-start")).toBeNull();
    expect(screen.queryByTestId("tab-strip-more-end")).toBeNull();

    geometry(0);
    expect(screen.getByTestId("tab-strip-more-end")).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByTestId("tab-strip-more-start")).toBeNull();

    geometry(80);
    expect(screen.getByTestId("tab-strip-more-start")).toBeInTheDocument();
    expect(screen.getByTestId("tab-strip-more-end")).toBeInTheDocument();

    geometry(169);
    expect(screen.getByTestId("tab-strip-more-start")).toBeInTheDocument();
    expect(screen.queryByTestId("tab-strip-more-end")).toBeNull();
  });

  it("badges the Optimize tab with the tweaks not optimized across software, hardware and games", () => {
    // One page owns all three now, so one number says how much is left on it;
    // an advisory, a cleanup and a setting already right are not part of it.
    const row = (id: string, over: Partial<Setting> = {}) =>
      [
        id,
        {
          id,
          isApplicable: true,
          isAction: false,
          isReadonly: false,
          currentValue: "on",
          status: "suboptimal",
          isOptimized: false,
          ...over,
        } as Setting,
      ] as const;
    useStore.setState({
      activeTab: "optimize",
      settings: new Map([
        row("network:nagle", { domain: "software" }),
        row("gpu-hardware:hags", { domain: "hardware" }),
        row("game_config:mw4:shadow", { domain: "game" }),
        row("network:rss", { status: "optimal", isOptimized: true }),
        row("network:link", { isReadonly: true }),
        row("cleanup:cache", { isAction: true }),
      ]),
    } as never);
    render(<TabNavigation />);

    expect(within(screen.getByRole("tab", { name: /Optimize/ })).getByText("3")).toBeInTheDocument();
    // Nothing else on the strip carries a number.
    expect(within(screen.getByRole("tab", { name: /Cleanup/ })).queryByText(/^\d+$/)).toBeNull();
    expect(within(screen.getByRole("tab", { name: /Measure/ })).queryByText(/^\d+$/)).toBeNull();
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
