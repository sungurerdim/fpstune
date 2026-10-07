/**
 * TweakRow: one setting, one line.
 *
 * The row exists to answer "what is not optimized, and how do I fix it" at a
 * glance, so each case names the way it would stop answering: a state worded
 * "enabled → disabled" that does not say what the user sees, an optimized row
 * as loud as a broken one, an Apply that two rows share the name of, a name or
 * value that wraps and makes the list twice as tall, a control a keyboard cannot
 * reach.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setLocale } from "../../i18n";
import {
  CATALOGUE,
  UNBROKEN,
  advisoryProbes,
  narrowAdvisory,
  narrowReport,
  narrowSetting,
} from "../../test/narrow";
import type { Setting } from "../../types/setting";
import { TweakRow, type TweakRowProps } from "../TweakRow";

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "network:nagle_algorithm" as Setting["id"],
    domain: "software",
    module: "network",
    name: "nagle_algorithm",
    displayName: "Nagle's algorithm",
    description: "Batches small packets before sending them.",
    category: "network",
    valueType: "choice",
    choices: ["enabled", "disabled"],
    defaultValue: "disabled",
    recommendedValue: "enabled",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    impactCategories: [],
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "proven",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    // "Off" and "On" are what the user sees, not the stored words.
    choiceLabels: { enabled: "tier.on", disabled: "tier.off" },
    currentValue: "disabled",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...overrides,
  };
}

function renderRow(setting: Setting, props: Partial<TweakRowProps> = {}) {
  const onApply = vi.fn();
  const onReset = vi.fn();
  const view = render(
    <TweakRow setting={setting} onApply={onApply} onReset={onReset} {...props} />,
  );
  return { onApply, onReset, ...view };
}

const row = () => screen.getByTestId("tweak-row");
const apply = () => screen.queryByRole("button", { name: /^Apply / });
const info = () => screen.getByRole("button", { name: /^Information about|hakkında bilgi$/ });
/** The row's line: the (i) is a direct child of it. */
const line = () => info().parentElement as HTMLElement;

afterEach(() => setLocale("en"));

describe("the state is worded as values, and the fix is one press", () => {
  it("reads 'Off → On', not enabled/disabled, for what the user is on and what is recommended", () => {
    renderRow(makeSetting());

    expect(screen.getByTitle("Off → On")).toBeInTheDocument();
    // Screen readers get words, not an arrow: "Off → On" read aloud is noise.
    expect(row()).toHaveTextContent("Currently Off");
    expect(row()).toHaveTextContent(", recommended value is On");
  });

  it("Apply writes the recommended value, and its name says which setting it changes", async () => {
    const { onApply } = renderRow(makeSetting());

    const button = screen.getByRole("button", { name: "Apply Nagle's algorithm" });
    await userEvent.click(button);

    expect(onApply).toHaveBeenCalledExactlyOnceWith("enabled");
  });

  it("gives two rows two different Apply names — a list of 'Apply, Apply, Apply' is unusable aloud", () => {
    render(
      <>
        <TweakRow setting={makeSetting()} onApply={vi.fn()} onReset={vi.fn()} />
        <TweakRow
          setting={makeSetting({ id: "network:tcp_ack" as Setting["id"], displayName: "TCP ACK frequency" })}
          onApply={vi.fn()}
          onReset={vi.fn()}
        />
      </>,
    );

    expect(screen.getByRole("button", { name: "Apply Nagle's algorithm" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply TCP ACK frequency" })).toBeInTheDocument();
  });
});

describe("what needs work is loud, what is right is quiet", () => {
  it("tints a row that is not optimized and carries Apply", () => {
    renderRow(makeSetting());

    expect(row()).toHaveAttribute("data-optimal", "false");
    expect(row()).toHaveClass("border-l-warning");
    expect(apply()).toBeInTheDocument();
  });

  it("leaves an optimized row with nothing to press, and says so in words, not only colour", () => {
    renderRow(makeSetting({ currentValue: "enabled", isOptimized: true }));

    expect(row()).toHaveAttribute("data-optimal", "true");
    expect(row()).not.toHaveClass("border-l-warning");
    expect(apply()).toBeNull();
    expect(row()).toHaveTextContent("Already at the recommended value: On");
  });

  it("takes 'optimized' from the backend and never recomputes it from the two values", () => {
    // Current differs from recommended, yet the backend says optimized (it
    // knows an equivalence the frontend does not): the row must believe it.
    renderRow(makeSetting({ currentValue: "disabled", recommendedValue: "enabled", isOptimized: true }));

    expect(row()).toHaveAttribute("data-optimal", "true");
    expect(apply()).toBeNull();
  });

  it("shows a setting that does not apply as N/A, dimmed, with nothing to press", () => {
    renderRow(makeSetting({ isApplicable: false }), { onSelect: vi.fn() });

    expect(row()).toHaveTextContent("N/A");
    expect(row()).toHaveClass("opacity-60");
    expect(apply()).toBeNull();
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });

  it("shows a setting still being read as reading, not as 'not optimized'", () => {
    renderRow(makeSetting({ status: "loading", currentValue: null }));

    expect(row()).not.toHaveAttribute("data-optimal");
    expect(row()).toHaveTextContent("Reading…");
    expect(apply()).toBeNull();
  });

  it("says 'Not read' when the check came back with no value", () => {
    renderRow(makeSetting({ currentValue: null, status: "error" }));

    expect(screen.getByTitle("Not read → On")).toBeInTheDocument();
  });
});

describe("risk is its own chip, only when it is advanced", () => {
  it.each([
    ["safe", false],
    ["low", false],
    ["moderate", false],
    ["advanced", true],
  ] as const)("%s → chip shown: %s", (riskLevel, shown) => {
    renderRow(makeSetting({ riskLevel, riskWarning: "Can drop the link." }));

    expect(screen.queryByTestId("risk-chip") !== null).toBe(shown);
  });
});

describe("selection", () => {
  it("has a checkbox named after the setting when the page asks for one, and reports the toggle", async () => {
    const onSelect = vi.fn();
    renderRow(makeSetting(), { onSelect });

    await userEvent.click(screen.getByRole("checkbox", { name: "Select Nagle's algorithm" }));

    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("reflects the page's selection", () => {
    renderRow(makeSetting(), { onSelect: vi.fn(), selected: true });

    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("has no checkbox when the page gave no way to select", () => {
    renderRow(makeSetting());

    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("never offers to select a read-only row: there is nothing to apply to it", () => {
    renderRow(makeSetting({ isReadonly: true }), { onSelect: vi.fn() });

    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(apply()).toBeNull();
  });
});

describe("the keyboard reaches everything on the line", () => {
  it("tabs checkbox → Apply → (i), and each works from the keyboard", async () => {
    const onSelect = vi.fn();
    const { onApply } = renderRow(makeSetting(), { onSelect });

    await userEvent.tab();
    expect(screen.getByRole("checkbox")).toHaveFocus();
    await userEvent.keyboard(" ");
    expect(onSelect).toHaveBeenCalledTimes(1);

    await userEvent.tab();
    expect(apply()).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onApply).toHaveBeenCalledWith("enabled");

    await userEvent.tab();
    expect(info()).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(info()).toHaveAttribute("aria-expanded", "true");
  });

  it("gives every control an accessible name", () => {
    renderRow(makeSetting({ choices: ["low", "medium", "high"], choiceLabels: undefined }), {
      onSelect: vi.fn(),
    });

    for (const control of [
      ...screen.getAllByRole("button"),
      ...screen.getAllByRole("checkbox"),
      ...screen.getAllByRole("combobox"),
    ]) {
      expect(control, control.outerHTML).toHaveAccessibleName();
    }
  });
});

describe("the (i) opens the detail under the row, and the row stays one line", () => {
  it("opens the panel inside the row, not in the line", async () => {
    renderRow(makeSetting({ description: "Batches small packets before sending them." }));

    await userEvent.click(info());

    const panel = screen.getByRole("region");
    expect(row()).toContainElement(panel);
    expect(line()).not.toContainElement(panel);
    expect(panel).toHaveTextContent("Batches small packets");
  });

  it("puts the reset in the detail, not on the line", async () => {
    const { onReset } = renderRow(makeSetting({ currentValue: "enabled", isOptimized: true }));
    expect(within(line()).queryByRole("button", { name: /Reset/ })).toBeNull();

    await userEvent.click(info());
    await userEvent.click(screen.getByRole("button", { name: /^Reset .* to default/ }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });
});

describe("a choice of three or more is picked in the row", () => {
  const picker = () => screen.queryByRole("combobox", { name: "Choose a value for Nagle's algorithm" });
  const threeWay = (extra: Partial<Setting> = {}) =>
    makeSetting({
      choices: ["low", "medium", "high"],
      choiceLabels: undefined,
      defaultValue: "medium",
      currentValue: "low",
      recommendedValue: "high",
      ...extra,
    });

  it("writes the picked value, not the recommended one", async () => {
    const { onApply } = renderRow(threeWay());

    await userEvent.selectOptions(picker()!, "medium");

    expect(onApply).toHaveBeenCalledExactlyOnceWith("medium");
  });

  it("shows the value the machine is on as the selection, with the recommendation beside it", () => {
    renderRow(threeWay());

    expect(picker()).toHaveValue("low");
    expect(row()).toHaveTextContent("recommended value is high");
  });

  it("drops the recommendation once the machine is there", () => {
    renderRow(threeWay({ currentValue: "high", isOptimized: true }));

    expect(picker()).toHaveValue("high");
    expect(row()).not.toHaveTextContent("recommended value is");
  });

  it("selects nothing rather than the first option when the value is not one of the choices", () => {
    renderRow(threeWay({ currentValue: "turbo" }));

    expect(picker()).toHaveValue("");
  });

  it("has no picker for two choices: Apply and Reset to default are the whole story", () => {
    renderRow(makeSetting());

    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("is not offered on a read-only row", () => {
    renderRow(threeWay({ isReadonly: true }));

    expect(screen.queryByRole("combobox")).toBeNull();
  });
});

describe("a run on this row", () => {
  it("shows Apply busy and unpressable while it runs", () => {
    renderRow(makeSetting(), { status: "running" });

    expect(apply()).toBeDisabled();
    expect(apply()).toHaveAttribute("aria-busy", "true");
  });

  it("says why a run failed, to a screen reader and on hover", () => {
    renderRow(makeSetting(), { status: "failed", error: "Access is denied." });

    const mark = screen.getByRole("img", { name: "Failed: Access is denied." });
    expect(mark).toHaveAttribute("title", "Access is denied.");
  });

  it("marks a verified row, a queued row and a skipped row", () => {
    const { rerender } = renderRow(makeSetting(), { status: "verified" });
    expect(screen.getByRole("img", { name: "Applied and verified" })).toBeInTheDocument();

    rerender(<TweakRow setting={makeSetting()} onApply={vi.fn()} onReset={vi.fn()} status="queued" />);
    expect(row()).toHaveTextContent("queued");

    rerender(<TweakRow setting={makeSetting()} onApply={vi.fn()} onReset={vi.fn()} status="skipped" />);
    expect(row()).toHaveTextContent("skipped");
  });

  it("passes the failure into the detail", async () => {
    renderRow(makeSetting(), { status: "failed", error: "Access is denied." });

    await userEvent.click(info());

    expect(screen.getByRole("region")).toHaveTextContent("Access is denied.");
  });
});

// ---------------------------------------------------------------------------
// One line at the narrowest width, in both languages.
// ---------------------------------------------------------------------------

/**
 * jsdom measures nothing, so "one line" is asserted as what makes a browser
 * keep it on one: no wrapping container on the line, and every phrase on it
 * clipped by `truncate` instead of allowed to flow onto a second line.
 */
function wrapping(root: HTMLElement): string[] {
  const found: string[] = [];
  for (const el of [root, ...Array.from(root.querySelectorAll("*"))]) {
    const wraps = Array.from(el.classList).filter((c) => /^(flex-wrap|flex-wrap-reverse|flex-col)$/.test(c));
    if (wraps.length) found.push(`<${el.tagName.toLowerCase()}> ${wraps.join(" ")}`);
    if (el.tagName === "OPTION" || el.closest(".sr-only") || el.closest("select")) continue;
    const own = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent ?? "")
      .join("")
      .trim();
    if (/\s/.test(own) && !el.closest(".truncate")) found.push(`phrase not clipped: "${own}"`);
  }
  return found;
}

describe.each(["en", "tr"] as const)("one line at the narrowest width (%s)", (locale) => {
  const KINDS = ["unbroken", "catalogue"] as const;

  it.each(KINDS)("clips a long name and a long value instead of wrapping them: %s", (kind) => {
    setLocale(locale);
    const setting = narrowSetting(kind, {
      choiceLabels: undefined,
      riskLevel: "advanced",
      riskWarning: "risk",
      currentValue: kind === "unbroken" ? UNBROKEN : CATALOGUE.description,
    });
    const { container } = renderRow(setting, { onSelect: vi.fn(), status: "queued" });

    expect(wrapping(line())).toEqual([]);
    const name = line().querySelector("span.truncate") as HTMLElement;
    expect(name.getAttribute("title")).toBe(name.textContent);
    expect(name.textContent).toBe(kind === "unbroken" ? UNBROKEN : CATALOGUE.name);

    const probes: Record<string, string> =
      kind === "unbroken"
        ? { token: UNBROKEN }
        : { name: CATALOGUE.name, description: CATALOGUE.description };
    const { violations, carriers } = narrowReport(container, probes);
    expect(Object.values(carriers).some((n) => n > 0), "the row drew a probe").toBe(true);
    expect(violations).toEqual([]);
  });

  it.each(KINDS)("keeps the open detail inside the frame too: %s", async (kind) => {
    setLocale(locale);
    const { container } = renderRow(narrowSetting(kind, { choiceLabels: undefined }));
    await userEvent.click(info());

    const probes: Record<string, string> =
      kind === "unbroken"
        ? { token: UNBROKEN }
        : { name: CATALOGUE.name, description: CATALOGUE.description, effect: CATALOGUE.effect };
    const { violations, carriers } = narrowReport(container, probes);

    expect(Object.values(carriers).every((n) => n > 0), JSON.stringify(carriers)).toBe(true);
    expect(violations).toEqual([]);
  });

  it("clips an advisory's long state phrase, and the detail carries the instruction", async () => {
    setLocale(locale);
    const setting = narrowAdvisory();
    const { container } = renderRow(setting);
    await userEvent.click(info());

    expect(wrapping(line())).toEqual([]);
    const { violations, carriers } = narrowReport(container, advisoryProbes(setting));

    expect(Object.values(carriers).every((n) => n > 0), JSON.stringify(carriers)).toBe(true);
    expect(violations).toEqual([]);
  });
});
