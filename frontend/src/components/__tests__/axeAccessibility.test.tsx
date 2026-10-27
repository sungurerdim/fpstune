/**
 * P-WCAG, the rendered-tree half.
 *
 * `eslint-plugin-jsx-a11y` checks the source (a click on a div with no key
 * handler, an aria-* attribute a role does not allow). It cannot see what the
 * user actually gets: an accessible name assembled from several children, a
 * live region that announces nothing, a heading level that skips. axe runs over
 * the rendered DOM and answers that question, and these four surfaces are the
 * interactive ones where a wrong answer costs a user the ability to act:
 *
 * - `TweakRow` — every tweak on the Optimize tab is one, each with its own Apply.
 * - `ConfirmDialog` — the one modal gate before a bulk apply.
 * - `SelectionToolbar` — the one bulk bar, including its disabled-count buttons.
 * - `NotificationToasts` — the only channel for a failure the user must act on.
 *
 * What axe cannot check here is colour contrast: jsdom has no layout and no
 * computed styles, so axe skips the contrast rules by itself. That gap is real
 * and is covered by the Playwright + @axe-core/playwright suite (`npm run
 * test:a11y`), which runs against a real browser; it is recorded here rather
 * than papered over with a disabled rule.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render } from "../../test/utils";
import { axe } from "vitest-axe";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";
import { TweakRow } from "../TweakRow";
import { SelectionToolbar } from "../SelectionToolbar";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { NotificationToasts } from "../ui/NotificationToasts";

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "power:cpu_min_state" as `${string}:${string}`,
    domain: "software",
    module: "power",
    name: "cpu_min_state",
    displayName: "Minimum Processor State",
    description: "Lowest clock speed the CPU is allowed to drop to when idle.",
    category: "power",
    valueType: "int",
    choices: [],
    defaultValue: 5,
    recommendedValue: 5,
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    impactCategories: ["thermal"],
    categoryOrder: 13,
    riskLevel: "low",
    evidenceLevel: "proven",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: 100,
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...overrides,
  };
}

beforeEach(() => {
  useStore.setState({
    settings: new Map(),
    selectedSettingIds: new Set(),
    operationStatus: {},
    operationError: {},
    notifications: [],
  } as never);
});

describe("TweakRow", () => {
  it("has no axe violations for a row that needs work", async () => {
    const { container } = render(
      <TweakRow setting={makeSetting()} onApply={vi.fn()} onReset={vi.fn()} />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("has no axe violations for an optimized, selectable row with a status mark", async () => {
    const { container } = render(
      <TweakRow
        setting={makeSetting({
          isOptimized: true,
          currentValue: 5,
          status: "optimal",
        })}
        onApply={vi.fn()}
        onReset={vi.fn()}
        selected
        onSelect={vi.fn()}
        status="verified"
      />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("ConfirmDialog", () => {
  it("has no axe violations while it is the open question", async () => {
    render(
      <ConfirmDialog
        open
        title="Restart Docker & WSL?"
        confirmLabel="Prune & compact"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      >
        Everything will be shut down and restarted.
      </ConfirmDialog>,
    );

    // The dialog is portalled to document.body and the page behind it is marked
    // inert; the question itself is what a user must be able to answer.
    expect(await axe(document.body)).toHaveNoViolations();
  });
});

describe("SelectionToolbar", () => {
  it("has no axe violations with a row selected", async () => {
    const setting = makeSetting();
    useStore.setState({
      settings: new Map([[setting.id, setting]]),
      selectedSettingIds: new Set([setting.id]),
    } as never);

    const { container } = render(<SelectionToolbar />);

    expect(await axe(container)).toHaveNoViolations();
  });

  it("has no axe violations with its scope buttons on screen", async () => {
    const settings = [
      makeSetting(),
      makeSetting({
        id: "power:cpu_idle_states" as `${string}:${string}`,
        name: "cpu_idle_states",
        displayName: "CPU Idle States",
      }),
    ];
    useStore.setState({
      settings: new Map(settings.map((s) => [s.id, s])),
      selectedSettingIds: new Set(),
    } as never);

    const { container } = render(<SelectionToolbar settings={settings} name="Software" />);

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("NotificationToasts", () => {
  it("has no axe violations with an error and a success on screen", async () => {
    useStore.setState({
      notifications: [
        { id: "n1", message: "Cannot reach the backend.", type: "error" },
        { id: "n2", message: "Cleanup complete.", type: "success" },
      ],
    } as never);

    const { container } = render(<NotificationToasts />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
