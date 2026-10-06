/**
 * Long text never spills: every list and row surface, held to one rule set.
 *
 * Commit e957523 fixed seven layout defects found by a browser sweep, and the
 * three text-overflow ones (an unbroken token spilling out of a cleanup row, a
 * clipped name with no way to read it, a flex item that would not shrink under
 * it) were pinned one component at a time. A new row added later is guarded by
 * nothing, which is how the class came back the first time. This file puts
 * every surface that lists user-visible text through `narrowReport` (the rules
 * live in `test/narrow.ts`) with two kinds of long input: a token no space can
 * break, and the longest real Turkish copy from `i18n/settingsTr.ts`, in both
 * locales.
 *
 * jsdom measures nothing; the rules read the classes that make the browser
 * behave. A surface needing its own state is one more entry in `SURFACES`; one
 * that does not is found in the source tree and rendered generically (see
 * `test/surfaces.ts`), so nothing depends on anyone remembering to list it.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import type { ComponentType, ReactElement } from "react";
import { setLocale } from "../../i18n";
import { useStore } from "../../store";
import { makeRunner } from "../../test/runner";
import {
  CATALOGUE,
  UNBROKEN,
  advisoryProbes,
  narrowAdvisory,
  narrowReport,
  narrowSetting,
} from "../../test/narrow";
import { discoverSurfaces, genericProps } from "../../test/surfaces";
import type { Setting } from "../../types/setting";
import { TweakRows } from "../TweakRows";
import { TweakListRow } from "../TweakListRow";
import { ActionRow } from "../ActionRow";
import { CleanupPanel } from "../CleanupPanel";
import { HistoryTab } from "../HistoryTab";
import { HomeTab } from "../HomeTab";
import { SettingInfoTooltip } from "../SettingInfoTooltip";

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

/**
 * `unbroken`: a token no space can break. `catalogue`: the longest real Turkish
 * copy. `advisory`: the unresolved Ethernet line-speed row, whose state, hint and
 * value labels are long *phrases* (the shape of the row that spilled).
 */
type Kind = "unbroken" | "catalogue" | "advisory";
const KINDS: Kind[] = ["unbroken", "catalogue", "advisory"];

/** The setting a surface is mounted with for one kind of long input. */
function fixture(kind: Kind, overrides: Partial<Setting> = {}): Setting {
  return kind === "advisory" ? narrowAdvisory(overrides) : narrowSetting(kind, overrides);
}

interface Surface {
  name: string;
  /** What to render for one kind of long input, and where the surface ends. */
  mount: (kind: Kind, long: string) => { ui: ReactElement; ready?: () => Promise<unknown> };
  /**
   * Probes this surface must actually show, by kind: a probe nobody drew proves
   * nothing. A kind absent here is one the surface does not render (a cleanup
   * action has no advisory state), and is not run.
   */
  expects: Partial<Record<Kind, string[]>>;
  /** Where the checked content lives; default is the render container. */
  root?: () => Element;
}

function seed(settings: Setting[], extra: Record<string, unknown> = {}) {
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
    ...extra,
  } as never);
}

/** Wait for the first 20 characters of the long text to be drawn (a plain substring, not a pattern). */
function findLong(long: string) {
  const head = long.slice(0, 20);
  return screen.findAllByText((content) => content.includes(head));
}

function longProbe(kind: Kind): string {
  if (kind === "advisory") return advisoryProbes(narrowAdvisory()).advisoryHint;
  return kind === "unbroken" ? UNBROKEN : CATALOGUE.description;
}

const SURFACES: Surface[] = [
  {
    name: "TweakRows (TweakSetting)",
    mount: (kind, long) => {
      const setting = fixture(kind);
      seed([setting], { operationError: { [setting.id]: long } });
      return {
        ui: (
          <TweakRows
            rows={[{ setting, contextLabel: long, contextIcon: <span /> }]}
          />
        ),
      };
    },
    expects: {
      unbroken: ["token"],
      catalogue: ["description", "name"],
      advisory: ["advisoryName", "advisoryState", "advisoryTarget", "advisoryHint"],
    },
  },
  {
    name: "TweakListRow (Home row)",
    mount: (kind, long) => {
      const setting = fixture(kind);
      seed([setting]);
      return { ui: <TweakListRow setting={setting} categoryLabel={long} /> };
    },
    expects: {
      unbroken: ["token"],
      catalogue: ["description", "name"],
      advisory: ["advisoryName", "advisoryState", "advisoryTarget"],
    },
  },
  {
    name: "ActionRow",
    mount: (kind, long) => {
      const setting = fixture(kind, {
        id: "cleanup:narrow_probe" as Setting["id"],
        module: "cleanup",
        isAction: true,
        valueType: "bool",
        choices: [],
        currentValue: "ready|4096 MB",
      });
      seed([setting], {
        runSteps: [
          {
            id: setting.id,
            name: long,
            status: "failed",
            command: long,
            percent: null,
            reportsProgress: false,
            durationEstimate: "",
            lines: [long],
            startedAt: 1,
            endedAt: 2,
          },
        ],
        cleanupResults: {
          [setting.id]: {
            id: setting.id,
            name: long,
            success: false,
            sized: true,
            freedMB: null,
            error: long,
          },
        },
      });
      return { ui: <ActionRow setting={setting} runner={makeRunner()} selectable /> };
    },
    expects: { unbroken: ["token"], catalogue: ["description"] },
  },
  {
    name: "CleanupPanel (group heading and rows)",
    mount: (kind, long) => {
      const setting = fixture(kind, {
        id: "cleanup:narrow_probe" as Setting["id"],
        module: "cleanup",
        isAction: true,
        valueType: "bool",
        choices: [],
        currentValue: "ready|4096 MB",
        groupId: "narrow",
        groupLabel: long,
        groupOrder: 1,
      });
      seed([setting]);
      return {
        // The panel's own title and description are static catalogue copy; the
        // text that varies is the backend's group label and each row's.
        ui: <CleanupPanel runner={makeRunner()} initialCollapsed={false} />,
      };
    },
    expects: { unbroken: ["token"], catalogue: ["description"] },
  },
  {
    name: "HistoryTab",
    mount: (kind, long) => {
      const setting = fixture(kind);
      seed([setting], {
        operationStatus: { [setting.id]: "failed" },
        operationError: { [setting.id]: long },
      });
      history.settings = [
        { setting_id: setting.id, last_action: "apply", value: long, at: 1_759_650_000 },
        { setting_id: `network:${long}`, last_action: "apply", value: long, at: 1_759_650_000 },
      ];
      return {
        ui: <HistoryTab />,
        ready: () => findLong(long),
      };
    },
    expects: { unbroken: ["token"], catalogue: ["description"] },
  },
  {
    name: "HomeTab groups",
    mount: (kind, long) => {
      const software = fixture(kind);
      const hardware = fixture(kind, {
        id: `gpu-nvidia:${software.name}` as Setting["id"],
        module: "gpu-nvidia",
        domain: "hardware",
        component: "gpu",
      });
      const game = fixture(kind, {
        id: `game_config:mw4:${software.name}` as Setting["id"],
        module: "game_config",
        domain: "game",
      });
      const advisory =
        kind === "advisory"
          ? narrowAdvisory()
          : narrowSetting(kind, {
              id: `network:12:${software.name}` as Setting["id"],
              module: "network",
              domain: "hardware",
              component: "network_adapter",
              isReadonly: true,
              currentValue: "weak_signal",
              recommendedValue: "good",
            });
      seed([software, hardware, game, advisory]);
      return { ui: <HomeTab />, ready: () => findLong(long) };
    },
    expects: {
      unbroken: ["token"],
      catalogue: ["description"],
      advisory: ["advisoryName", "advisoryState", "advisoryTarget", "advisoryHint"],
    },
  },
  {
    name: "SettingInfoTooltip",
    mount: (kind) => {
      const setting = fixture(kind, { sources: [`https://example.com/${UNBROKEN}`] });
      seed([setting]);
      return {
        ui: <SettingInfoTooltip setting={setting} />,
        ready: async () => {
          await userEvent.tab();
          return findLong(longProbe(kind));
        },
      };
    },
    root: () => document.body,
    expects: { unbroken: ["token"], catalogue: ["description"] },
  },
];

function probesFor(kind: Kind): Record<string, string> {
  if (kind === "advisory") return advisoryProbes(narrowAdvisory());
  return kind === "unbroken"
    ? { token: UNBROKEN }
    : { name: CATALOGUE.name, description: CATALOGUE.description, effect: CATALOGUE.effect };
}

describe.each(["en", "tr"] as const)("long text at narrow widths (%s)", (locale) => {
  beforeEach(() => setLocale(locale));
  afterEach(() => setLocale("en"));

  describe.each(SURFACES)("$name", (surface) => {
    it.each(KINDS.filter((k) => surface.expects[k]))(
      "keeps %s text inside its row",
      async (kind) => {
        // The probe shown for a Turkish row is the catalogue's own form; in
        // English the fixtures put the same strings in the English fields.
        const long = longProbe(kind);
        const { ui, ready } = surface.mount(kind, long);
        const view = render(ui);
        await ready?.();

        const root = surface.root?.() ?? view.container;
        const probes = probesFor(kind);
        const { violations, carriers } = narrowReport(root, probes);

        // A probe that was never drawn proves nothing: the surface must show
        // the text this test claims to have checked.
        for (const label of surface.expects[kind] ?? []) {
          expect(carriers[label], `${surface.name} never drew the ${label} probe`).toBeGreaterThan(0);
        }
        expect(violations).toEqual([]);
      },
    );
  });
});

// ---------------------------------------------------------------------------
// Coverage derived from the code, not from a list.
// ---------------------------------------------------------------------------

/**
 * Components that import the `Setting` type and still cannot be put through the
 * generic render, each with the reason. The list is a *debt register*, not a
 * way out: an entry whose component now renders generically fails (stale), and
 * so does one naming a component that no longer exists.
 */
const NOT_GENERIC: Record<string, string> = {
  "components/ScopeActions.tsx#ScopeActions":
    "Icon buttons: the scope's name reaches a screen reader through aria-label and a tooltip, and nothing on screen carries setting text.",
  "components/SelectionToolbar.tsx#SelectionToolbar":
    "Draws a selection count and fixed labels; no setting text is rendered, only how many are selected.",
  "components/SettingStateDisplay.tsx#ImpactCategoryTags":
    "Draws the fixed short category labels (fps, latency, heat); a setting's own text never reaches it.",
  "components/SettingStateDisplay.tsx#RiskWarningBadge":
    "Draws the fixed NOTE / RISK badge; the warning text is a title attribute, which takes no room on screen.",
};

/** Components mounted by hand above, with the state they need. */
const BESPOKE = new Set([
  "TweakRows",
  "TweakListRow",
  "ActionRow",
  "CleanupPanel",
  "HistoryTab",
  "HomeTab",
  "SettingInfoTooltip",
]);

/** One setting per way a surface may meet it: plain, game, maintenance, and unreadable. */
function genericSettings(kind: Kind): Setting[] {
  if (kind === "advisory") return [narrowAdvisory()];
  const base = fixture(kind);
  const sibling = (module: string, extra: Partial<Setting>) =>
    fixture(kind, { id: `${module}:${base.name}` as Setting["id"], module, ...extra });
  return [
    base,
    sibling("game_config", { id: `game_config:mw4:${base.name}` as Setting["id"], domain: "game" }),
    sibling("maintenance", { isAction: true, valueType: "bool", choices: [], currentValue: "ready|4096 MB" }),
    sibling("network", {
      detectionError: longProbe(kind),
      isApplicable: false,
      domain: "hardware",
      component: "network_adapter",
    }),
  ];
}

function renderGeneric(Component: ComponentType<Record<string, unknown>>, kind: Kind) {
  const long = longProbe(kind);
  const settings = genericSettings(kind);
  seed(settings, { selectedSettingIds: new Set(settings.map((s) => s.id)) });
  const view = render(<Component {...genericProps(settings, long)} />);
  // What a surface keeps behind a disclosure is still a surface: open them all,
  // twice, so a fold inside a fold is drawn too.
  for (let pass = 0; pass < 2; pass += 1) {
    for (const closed of view.container.querySelectorAll('[aria-expanded="false"]')) {
      fireEvent.click(closed);
    }
  }
  const { violations, carriers } = narrowReport(view.container, probesFor(kind));
  const drawn = Object.values(carriers).reduce((a, b) => a + b, 0);
  view.unmount();
  return { violations, drawn };
}

describe.each(["en", "tr"] as const)("every surface that renders a setting (%s)", (locale) => {
  beforeEach(() => setLocale(locale));
  afterEach(() => setLocale("en"));

  const found = discoverSurfaces();
  const generic = found.filter((c) => !BESPOKE.has(c.name) && !(c.id in NOT_GENERIC));

  it("finds the surfaces in the source tree", () => {
    // A discovery that silently finds nothing would pass everything below.
    expect(found.length).toBeGreaterThan(BESPOKE.size);
    for (const name of BESPOKE) {
      expect(
        found.some((c) => c.name === name),
        `${name} is mounted by hand but no longer imports the Setting type`,
      ).toBe(true);
    }
  });

  it.each(generic.map((c) => [c.id, c] as const))("%s keeps long text inside its frame", (_id, c) => {
    const violations: string[] = [];
    let drawn = 0;
    for (const kind of KINDS) {
      const result = renderGeneric(c.Component, kind);
      violations.push(...result.violations);
      drawn += result.drawn;
    }
    expect(violations).toEqual([]);
    // Rendering none of the long text proves nothing: either the generic props
    // are missing one this component needs, or it shows no setting text at all.
    // Either way it is named in NOT_GENERIC with the reason, not passed.
    expect(drawn, `${c.id} drew none of the long text: add it to NOT_GENERIC with a reason`).toBeGreaterThan(0);
  });

  it.each(Object.entries(NOT_GENERIC))("exclusion %s is not stale", (id, reason) => {
    const c = found.find((f) => f.id === id);
    expect(c, `${id} is excluded but no longer exists or no longer imports Setting`).toBeDefined();
    expect(reason.trim().length, `${id} is excluded without a reason`).toBeGreaterThan(20);
    let drawn = 0;
    let threw = false;
    try {
      for (const kind of KINDS) drawn += renderGeneric(c!.Component, kind).drawn;
    } catch {
      threw = true;
    }
    expect(
      threw || drawn === 0,
      `${id} now renders the long text generically: delete its exclusion`,
    ).toBe(true);
  });
});
