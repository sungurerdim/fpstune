/**
 * A choice's name is the backend's, on every surface that prints one.
 *
 * `Setting.choiceLabels` (commit 574e6c1) says the NVIDIA low-latency tier
 * stored as `on` is called "Ultra" on a driver without the legacy keys. The
 * state line learned it; the pill selector, the toggle tooltip and the history
 * entry kept printing `on`, so one row said "Ultra" and its neighbour said
 * "on". This renders a setting that carries `choiceLabels` through every
 * surface `test/surfaces.ts` discovers and fails where the stored value shows
 * where its name should. `valueLabelSingleSource.test.ts` is the source-level
 * half: it catches a surface that formats a value by hand before it is drawn.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, within } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { setLocale } from "../../i18n";
import { useStore } from "../../store";
import { narrowSetting } from "../../test/narrow";
import { discoverSurfaces, genericProps } from "../../test/surfaces";
import type { Setting } from "../../types/setting";
import { TweakRows } from "../TweakRows";

const history = vi.hoisted(() => ({ settings: [] as unknown[] }));

vi.mock("../HardwarePanel", () => ({ HardwarePanel: () => null }));
vi.mock("../hardware/useHardware", () => ({
  useHardware: () => ({ hardware: null, isLoading: false }),
}));
vi.mock("../SelfCheckNotice", () => ({ SelfCheckNotice: () => null }));
vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: vi.fn(), isApplying: false }),
}));
vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({ run: vi.fn(), stop: vi.fn(), isRunning: false }),
}));
vi.mock("../../hooks/useCleanupRunner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../hooks/useCleanupRunner")>()),
  useCleanupRunner: () => ({
    selectedIds: [],
    selectedCount: 0,
    hasSelection: false,
    isRunning: false,
    run: vi.fn(),
    confirmIds: null,
    confirmRun: vi.fn(),
    cancelConfirm: vi.fn(),
  }),
}));
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    headroomApi: {
      list: () =>
        Promise.resolve({
          headroom: {
            is_measured: false,
            measured_fps: null,
            fps_1_percent_low: null,
            target_fps: null,
            achievement_percent: null,
            tier: "unknown",
            bottleneck: "unknown",
            present_mode: null,
            width: null,
            height: null,
            measured_at: null,
          },
        }),
    },
    historyApi: {
      get: () => Promise.resolve({ settings: history.settings, entries: [] }),
    },
  };
});

/** The words each locale prints for the stored values `off` and `on`. */
const NAMES = {
  en: { off: "Off", on: "Ultra" },
  tr: { off: "Kapalı", on: "Ultra" },
} as const;

/**
 * The values the row stores. Real ones are `off` and `on`, plain English words
 * that the static copy of Home and Game Tweaks uses too ("found on this
 * machine"), so a search for them reads that copy as a leak; these carry the
 * same shape and appear nowhere else.
 */
const RAW = { off: "ll_off", on: "ll_on", max: "ll_max" } as const;

/**
 * The NVIDIA low-latency row as a driver without the legacy keys reports it:
 * one stored value named "Ultra", another "Off". The stored words appear
 * nowhere else in the row's copy, so their appearance is the formatter skipped.
 */
function lowLatency(overrides: Partial<Setting> = {}): Setting {
  return narrowSetting("unbroken", {
    id: "gpu-nvidia:low_latency_mode" as Setting["id"],
    module: "gpu-nvidia",
    name: "low_latency_mode",
    domain: "hardware",
    component: "gpu",
    displayName: "Low latency mode",
    shortName: "Low latency",
    description: "Sets how many frames the driver queues for the GPU.",
    currentImpact: "Off: the driver queues frames ahead.",
    recommendedImpact: "Ultra: one frame queued, lower input delay.",
    effect: "Cuts the render queue",
    lastError: undefined,
    choices: [RAW.off, RAW.on],
    defaultValue: RAW.off,
    recommendedValue: RAW.on,
    currentValue: RAW.off,
    isOptimized: false,
    choiceLabels: { [RAW.off]: "tier.off", [RAW.on]: "tier.ultra" },
    ...overrides,
  });
}

function seed(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map(),
    selectedSettingIds: new Set(),
    operationStatus: {},
    operationError: {},
    cleanupResults: {},
    runSteps: [],
    maintenanceSelection: {},
    categoryDetectionStatus: { core: "success" },
  } as never);
}

/** Everything a person or a screen reader can take from a subtree: text, and the attributes that speak. */
function spoken(root: Element): string {
  const attributes = [...root.querySelectorAll("[title],[aria-label]")].flatMap((el) => [
    el.getAttribute("title") ?? "",
    el.getAttribute("aria-label") ?? "",
  ]);
  return [root.textContent ?? "", ...attributes].join("\n");
}

/** A stored value as a whole word, never its name ("Ultra", "Kapalı"). */
const STORED = new RegExp(String.raw`\b(?:${Object.values(RAW).join("|")})\b`);

describe.each(["en", "tr"] as const)("a named choice reaches every surface (%s)", (locale) => {
  beforeEach(() => setLocale(locale));
  afterEach(() => setLocale("en"));

  const names = NAMES[locale];

  it("finds the surfaces it sweeps", () => {
    // A discovery that finds nothing would pass the sweep below.
    expect(discoverSurfaces().length).toBeGreaterThan(5);
  });

  // The two-choice toggle and the three-choice pill selector draw different
  // controls, so each shape is swept through every surface.
  describe.each([
    ["a two-choice toggle", [RAW.off, RAW.on]],
    ["a three-choice pill selector", [RAW.off, RAW.on, RAW.max]],
  ] as const)("%s", (_shape, choices) => {
    it("prints no stored value on any surface that renders", async () => {
      history.settings = [];
      const settings = [
        lowLatency({ choices: [...choices] }),
        lowLatency({
          id: "gpu-nvidia:low_latency_ready" as Setting["id"],
          name: "low_latency_ready",
          choices: [...choices],
          currentValue: RAW.on,
          isOptimized: true,
        }),
      ];
      history.settings = settings.map((s) => ({
        setting_id: s.id,
        last_action: "apply",
        value: RAW.on,
        at: 1_759_650_000,
      }));

      const leaks: string[] = [];
      const drewName: string[] = [];
      for (const surface of discoverSurfaces()) {
        seed(settings);
        let view: ReturnType<typeof render>;
        try {
          view = render(<surface.Component {...genericProps(settings, "Probe")} />);
        } catch {
          continue; // needs state this generic bag lacks; the sweep names it below
        }
        // Past the first paint: HistoryTab fetches its rows.
        await new Promise((resolve) => setTimeout(resolve, 20));
        for (let pass = 0; pass < 2; pass += 1) {
          for (const closed of view.container.querySelectorAll('[aria-expanded="false"]')) {
            fireEvent.click(closed);
          }
        }
        const text = spoken(view.container);
        if (STORED.test(text)) leaks.push(`${surface.id}: ${text.match(STORED)?.[0]}`);
        if (text.includes(names.on)) drewName.push(surface.name);
        view.unmount();
      }

      expect(leaks, `a stored value is printed where its name belongs: ${leaks.join("; ")}`).toEqual([]);
      // The sweep proves nothing if no surface drew the name: the state line,
      // the row and the history entry are the ones it must reach.
      for (const must of ["TweakRows", "TweakListRow", "HistoryTab"]) {
        expect(drewName, `${must} never drew "${names.on}"`).toContain(must);
      }
    });
  });

  it("names the target on the toggle tooltip, and the default on its reset", async () => {
    const drifted = lowLatency();
    seed([drifted]);
    const first = render(<TweakRows rows={[{ setting: drifted }]} />);
    await userEvent.hover(within(first.container).getByRole("switch"));
    const setTo = locale === "en" ? `Set to ${names.on}` : `${names.on} yap`;
    expect((await screen.findAllByText(setTo)).length).toBeGreaterThan(0);
    expect(spoken(document.body)).not.toMatch(STORED);
    first.unmount();

    const optimal = lowLatency({ currentValue: RAW.on, isOptimized: true });
    seed([optimal]);
    const second = render(<TweakRows rows={[{ setting: optimal }]} />);
    await userEvent.hover(within(second.container).getByRole("switch"));
    const reset = locale === "en" ? `${names.off} (reset)` : `${names.off} (sıfırla)`;
    expect((await screen.findAllByText(reset)).length).toBeGreaterThan(0);
    expect(spoken(document.body)).not.toMatch(STORED);
  });

  it("names the pills, and the target pill's tooltip", async () => {
    const setting = lowLatency({ choices: [RAW.off, RAW.on, RAW.max] });
    seed([setting]);
    const view = render(<TweakRows rows={[{ setting }]} />);
    const pill = within(view.container).getByRole("button", { name: names.on });
    expect(within(view.container).getByRole("button", { name: names.off })).toBeInTheDocument();
    expect(spoken(view.container)).not.toMatch(STORED);

    // `on` is the recommended value and the row sits at `off`, so its pill is
    // the target and says so on hover.
    await userEvent.hover(pill);
    const target = locale === "en" ? "Target" : "Hedef";
    expect((await screen.findAllByText(`${target}: ${names.on}`)).length).toBeGreaterThan(0);
    expect(spoken(document.body)).not.toMatch(STORED);
  });
});
