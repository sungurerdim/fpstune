/**
 * CategorySection: a category folded to one line until it is asked for.
 *
 * The header is what answers "what is not optimized", so the cases here are the
 * ways that answer goes wrong: a count that includes manual steps nobody can
 * apply, one that counts a setting that does not exist on this machine, a
 * section open when the page promised a short list, a bulk button inside the
 * toggle (a button in a button), rows that reshuffle under the cursor.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setLocale } from "../../i18n";
import { CATALOGUE, UNBROKEN, narrowReport, narrowSetting } from "../../test/narrow";
import type { Setting } from "../../types/setting";
import { CategorySection, type CategorySectionProps } from "../CategorySection";

function makeSetting(name: string, overrides: Partial<Setting> = {}): Setting {
  return {
    id: `network:${name}` as Setting["id"],
    domain: "software",
    module: "network",
    name,
    displayName: `Setting ${name}`,
    description: "Does a thing.",
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
    currentValue: "disabled",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...overrides,
  };
}

const notOptimized = (name: string, extra: Partial<Setting> = {}) => makeSetting(name, extra);
const optimized = (name: string, extra: Partial<Setting> = {}) =>
  makeSetting(name, { currentValue: "enabled", isOptimized: true, status: "optimal", ...extra });
const manual = (name: string, extra: Partial<Setting> = {}) =>
  makeSetting(name, {
    isReadonly: true,
    effect: "Replace the cable.",
    choices: ["at_capability", "below_capability"],
    recommendedValue: "at_capability",
    defaultValue: "below_capability",
    currentValue: "below_capability",
    ...extra,
  });

function renderSection(settings: Setting[], props: Partial<CategorySectionProps> = {}) {
  const onApply = vi.fn();
  const onReset = vi.fn();
  const view = render(
    <CategorySection
      title="Network"
      settings={settings}
      onApply={onApply}
      onReset={onReset}
      {...props}
    />,
  );
  return { onApply, onReset, ...view };
}

const header = () => screen.getByRole("button", { name: /^Network/ });
const count = () => screen.queryByTestId("category-count");
const rows = () => screen.queryAllByTestId("tweak-row");
const manualToggle = () => screen.queryByRole("button", { name: /^Manual steps|^Elle yapılacaklar/ });

afterEach(() => setLocale("en"));

describe("closed by default, and the header answers the first question alone", () => {
  it("draws no rows until the section is opened", () => {
    renderSection([notOptimized("a"), optimized("b")]);

    expect(header()).toHaveAttribute("aria-expanded", "false");
    expect(rows()).toHaveLength(0);
  });

  it("says 'N of M not optimized' with the category's name, in one button", () => {
    renderSection([notOptimized("a"), notOptimized("b"), optimized("c")]);

    expect(count()).toHaveTextContent("2 of 3 not optimized");
    expect(header()).toHaveAccessibleName("Network 2 of 3 not optimized");
  });

  it("says everything is optimized instead of '0 of M not optimized'", () => {
    renderSection([optimized("a"), optimized("b")]);

    expect(count()).toHaveTextContent("All 2 optimized");
    expect(count()).toHaveAttribute("data-not-optimized", "0");
  });

  it("opens when the page says it has a reason to", () => {
    renderSection([notOptimized("a")], { defaultOpen: true });

    expect(header()).toHaveAttribute("aria-expanded", "true");
    expect(rows()).toHaveLength(1);
  });

  it("opens and closes with the button, from the keyboard too", async () => {
    renderSection([notOptimized("a"), optimized("b")]);

    header().focus();
    await userEvent.keyboard("{Enter}");
    expect(header()).toHaveAttribute("aria-expanded", "true");
    expect(rows()).toHaveLength(2);

    await userEvent.keyboard(" ");
    expect(header()).toHaveAttribute("aria-expanded", "false");
    expect(rows()).toHaveLength(0);
  });

  it("points aria-controls at the body only while there is one, and labels the body by the header", async () => {
    renderSection([notOptimized("a")]);
    expect(header()).not.toHaveAttribute("aria-controls");

    await userEvent.click(header());

    const body = screen.getByRole("group", { name: /^Network/ });
    expect(header().getAttribute("aria-controls")).toBe(body.id);
  });

  it("is a heading, so a screen reader can move between categories", () => {
    renderSection([notOptimized("a")]);

    expect(screen.getByRole("heading", { level: 3 })).toContainElement(header());
  });
});

describe("the counter counts tweaks, nothing else", () => {
  it("leaves read-only rows out of both numbers", () => {
    renderSection([
      notOptimized("a"),
      notOptimized("b"),
      optimized("c"),
      manual("m1"),
      manual("m2", { isOptimized: true, currentValue: "at_capability" }),
    ]);

    // 3 tweaks, 2 of them not optimized. The two advisories — one failing,
    // one fine — are manual steps: not tweaks, so not in either number.
    expect(count()).toHaveTextContent("2 of 3 not optimized");
  });

  it("leaves out a setting that does not exist on this machine", () => {
    renderSection([notOptimized("a"), notOptimized("gone", { isApplicable: false })]);

    expect(count()).toHaveTextContent("1 of 1 not optimized");
  });

  it("leaves out a cleanup action, which is never 'optimized'", () => {
    renderSection([notOptimized("a"), notOptimized("clean", { isAction: true })]);

    expect(count()).toHaveTextContent("1 of 1 not optimized");
  });

  it("does not call a setting not-optimized while it is still being read", () => {
    renderSection([
      notOptimized("a"),
      notOptimized("b", { status: "loading", currentValue: null }),
    ]);

    expect(count()).toHaveTextContent("1 of 1 not optimized");
  });

  it("says it is reading, rather than showing 0 of 0, when nothing is read yet", () => {
    renderSection([
      notOptimized("a", { status: "loading", currentValue: null }),
      notOptimized("b", { status: "loading", currentValue: null }),
    ]);

    expect(count()).toHaveTextContent("Reading…");
  });

  it("shows no count at all for a category that has only manual steps", () => {
    renderSection([manual("m1")]);

    expect(count()).toBeNull();
  });

  it("trusts the backend's isOptimized, not the two values", () => {
    renderSection([notOptimized("a", { isOptimized: true })]);

    expect(count()).toHaveTextContent("All 1 optimized");
  });
});

describe("manual steps: a trailing, collapsed, uncounted fold", () => {
  const settings = () => [notOptimized("a"), optimized("b"), manual("m1"), manual("m2")];

  it("is collapsed inside an open section, and names how many there are", async () => {
    renderSection(settings());
    await userEvent.click(header());

    expect(manualToggle()).toHaveTextContent("Manual steps (2)");
    expect(manualToggle()).toHaveAttribute("aria-expanded", "false");
    expect(rows()).toHaveLength(2);
  });

  it("is the last thing in the section", async () => {
    renderSection(settings());
    await userEvent.click(header());

    const body = screen.getByRole("group");
    expect(body.lastElementChild).toContainElement(manualToggle());
  });

  it("opens to the read-only rows, which carry no checkbox and no Apply", async () => {
    renderSection(settings(), { onSelect: vi.fn() });
    await userEvent.click(header());
    await userEvent.click(manualToggle()!);

    expect(manualToggle()).toHaveAttribute("aria-expanded", "true");
    expect(rows()).toHaveLength(4);
    const manualRow = rows()[2];
    expect(within(manualRow).queryByRole("checkbox")).toBeNull();
    expect(within(manualRow).queryByRole("button", { name: /^Apply / })).toBeNull();
    // The ordinary rows keep both.
    expect(within(rows()[0]).getByRole("checkbox")).toBeInTheDocument();
    expect(within(rows()[0]).getByRole("button", { name: /^Apply / })).toBeInTheDocument();
  });

  it("does not change the counter whether it is open or not", async () => {
    renderSection(settings());
    expect(count()).toHaveTextContent("1 of 2 not optimized");

    await userEvent.click(header());
    await userEvent.click(manualToggle()!);

    expect(count()).toHaveTextContent("1 of 2 not optimized");
  });

  it("does not exist when there are no read-only rows", async () => {
    renderSection([notOptimized("a")]);
    await userEvent.click(header());

    expect(manualToggle()).toBeNull();
  });
});

describe("the header's bulk action", () => {
  it("sits beside the toggle, not inside it — a button in a button is invalid and swallows clicks", () => {
    const onBulk = vi.fn();
    renderSection([notOptimized("a")], {
      actions: <button type="button" onClick={onBulk}>Apply recommended</button>,
    });

    const bulk = screen.getByRole("button", { name: "Apply recommended" });
    expect(header()).not.toContainElement(bulk);
    expect(header().querySelector("button")).toBeNull();
  });

  it("works while the section is closed, and does not open it", async () => {
    const onBulk = vi.fn();
    renderSection([notOptimized("a")], {
      actions: <button type="button" onClick={onBulk}>Apply recommended</button>,
    });

    await userEvent.click(screen.getByRole("button", { name: "Apply recommended" }));

    expect(onBulk).toHaveBeenCalledTimes(1);
    expect(header()).toHaveAttribute("aria-expanded", "false");
  });
});

describe("rows", () => {
  it("keeps the caller's order, so Apply never moves out from under the pointer", async () => {
    renderSection([optimized("z"), notOptimized("a"), optimized("m")]);
    await userEvent.click(header());

    expect(rows().map((r) => r.getAttribute("data-optimal"))).toEqual(["true", "false", "true"]);
  });

  it("hands the setting back with each callback", async () => {
    const a = notOptimized("a");
    const onSelect = vi.fn();
    const { onApply, onReset } = renderSection([a, optimized("b", { defaultValue: "disabled" })], {
      onSelect,
      defaultOpen: true,
    });

    await userEvent.click(screen.getByRole("button", { name: "Apply Setting a" }));
    expect(onApply).toHaveBeenCalledExactlyOnceWith(a, "enabled");

    await userEvent.click(screen.getByRole("checkbox", { name: "Select Setting a" }));
    expect(onSelect).toHaveBeenCalledExactlyOnceWith(a);

    await userEvent.click(screen.getByRole("button", { name: "Information about Setting b" }));
    await userEvent.click(screen.getByRole("button", { name: /^Reset Setting b to default/ }));
    expect(onReset).toHaveBeenCalledWith(expect.objectContaining({ name: "b" }));
  });

  it("checks the rows the page has selected, and only those", () => {
    renderSection([notOptimized("a"), notOptimized("b")], {
      onSelect: vi.fn(),
      selectedIds: new Set(["network:b"]),
      defaultOpen: true,
    });

    expect(screen.getByRole("checkbox", { name: "Select Setting a" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Select Setting b" })).toBeChecked();
  });

  it("gives each row its own run status and failure", () => {
    renderSection([notOptimized("a"), notOptimized("b")], {
      statuses: { "network:a": "running", "network:b": "failed" },
      errors: { "network:b": "Access is denied." },
      defaultOpen: true,
    });

    expect(screen.getByRole("button", { name: "Apply Setting a" })).toBeDisabled();
    expect(screen.getByRole("img", { name: "Failed: Access is denied." })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply Setting b" })).toBeEnabled();
  });
});

// ---------------------------------------------------------------------------
// One line at the narrowest width, in both languages.
// ---------------------------------------------------------------------------

describe.each(["en", "tr"] as const)("the header stays one line (%s)", (locale) => {
  it.each(["unbroken", "catalogue"] as const)("clips a long category name: %s", (kind) => {
    setLocale(locale);
    const long = kind === "unbroken" ? UNBROKEN : CATALOGUE.description;
    const { container } = render(
      <CategorySection
        title={long}
        settings={[narrowSetting(kind, { choiceLabels: undefined }), narrowSetting(kind, { isReadonly: true, choiceLabels: undefined })]}
        onApply={vi.fn()}
        onReset={vi.fn()}
        actions={<button type="button">Apply</button>}
        defaultOpen
      />,
    );

    const heading = screen.getByRole("heading", { level: 3 });
    for (const el of [heading, ...Array.from(heading.querySelectorAll("*"))]) {
      expect(Array.from(el.classList), `<${el.tagName}> wraps`).not.toContain("flex-wrap");
    }
    const name = heading.querySelector("span.truncate") as HTMLElement;
    expect(name.getAttribute("title")).toBe(long);

    const { violations, carriers } = narrowReport(container, { title: long });
    expect(carriers.title).toBeGreaterThan(0);
    expect(violations).toEqual([]);
  });

  it("keeps the counter on the line and clipped by the button, never wrapped", () => {
    setLocale(locale);
    renderSection([notOptimized("a"), notOptimized("b"), optimized("c")]);

    const counter = count()!;
    expect(counter).toHaveClass("whitespace-nowrap");
    expect(header()).toHaveClass("overflow-hidden");
    expect(header()).toContainElement(counter);
  });
});

describe("a category made of groups", () => {
  it("draws the groups in its body, and still counts every row inside", async () => {
    renderSection([notOptimized("a"), optimized("b")], {
      level: 2,
      children: <p>the groups</p>,
    });
    expect(count()).toHaveTextContent("1 of 2 not optimized");
    expect(screen.queryByText("the groups")).not.toBeInTheDocument();

    await userEvent.click(header());

    expect(screen.getByText("the groups")).toBeInTheDocument();
    // Its rows are the groups' to draw, not the section's own.
    expect(rows()).toHaveLength(0);
  });

  it("takes its place in the outline at the level it is given", () => {
    renderSection([notOptimized("a")], { level: 2 });

    expect(screen.getByRole("heading", { level: 2 })).toContainElement(header());
    expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
  });
});
