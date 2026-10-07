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
import { TweakRow } from "../TweakRow";


vi.mock("../hardware/useHardware", () => ({
  useHardware: () => ({ hardware: null, isLoading: false }),
}));
vi.mock("../SelfCheckNotice", () => ({ SelfCheckNotice: () => null }));
vi.mock("../../hooks/useApply", () => ({
  useApply: () => ({
    apply: vi.fn(),
    run: vi.fn(),
    reset: vi.fn(),
    stop: vi.fn(),
    pendingIds: new Set<string>(),
    isPending: () => false,
    isRunning: false,
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
  };
});

/** The words each locale prints for the stored values `off` and `on`. */
const NAMES = {
  en: { off: "Off", on: "Ultra" },
  tr: { off: "Kapalı", on: "Ultra" },
} as const;

/**
 * The values the row stores. Real ones are `off` and `on`, plain English words
 * that the static copy of the tweak lists uses too ("found on this
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
        // Past the first paint: some surfaces fetch their rows.
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
      // the row is the one it must reach.
      for (const must of ["TweakRow"]) {
        expect(drewName, `${must} never drew "${names.on}"`).toContain(must);
      }
    });
  });

  it("names the target on the row, and the default on its reset", async () => {
    const drifted = lowLatency();
    seed([drifted]);
    const first = render(<TweakRow setting={drifted} onApply={vi.fn()} onReset={vi.fn()} />);
    // What the machine is on and what is recommended, by their names.
    expect(within(first.container).getByTitle(`${names.off} → ${names.on}`)).toBeInTheDocument();
    expect(spoken(first.container)).not.toMatch(STORED);
    first.unmount();

    const optimal = lowLatency({ currentValue: RAW.on, isOptimized: true });
    seed([optimal]);
    const second = render(<TweakRow setting={optimal} onApply={vi.fn()} onReset={vi.fn()} />);
    await userEvent.click(within(second.container).getByRole("button", { name: /^Information about|hakkında bilgi$/ }));
    const reset = await screen.findByRole("button", {
      name: /^Reset .* to default|ayarını varsayılana döndür/,
    });
    // The button writes the default, and says which value that is.
    expect(reset).toHaveAccessibleName(new RegExp(names.off));
    expect(spoken(document.body)).not.toMatch(STORED);
  });

  it("names the options of the picker, and the recommended one beside the choice", async () => {
    const setting = lowLatency({ choices: [RAW.off, RAW.on, RAW.max] });
    seed([setting]);
    const view = render(<TweakRow setting={setting} onApply={vi.fn()} onReset={vi.fn()} />);

    const picker = within(view.container).getByRole("combobox");
    expect(within(picker).getByRole("option", { name: names.on })).toBeInTheDocument();
    expect(within(picker).getByRole("option", { name: names.off })).toBeInTheDocument();
    expect(spoken(view.container)).not.toMatch(STORED);

    // `on` is the recommended value and the row sits at `off`, so the row says
    // where it is going, by name.
    expect(within(view.container).getByText(names.on, { selector: "span" })).toBeInTheDocument();
  });
});
