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
 * behave. A new surface is one more entry in `SURFACES`.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { setLocale } from "../../i18n";
import { useStore } from "../../store";
import { makeRunner } from "../../test/runner";
import { CATALOGUE, UNBROKEN, narrowReport, narrowSetting } from "../../test/narrow";
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
vi.mock("../MaintenancePanel", () => ({ MaintenancePanel: () => null }));
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

type Kind = "unbroken" | "catalogue";

interface Surface {
  name: string;
  /** What to render for one kind of long input, and where the surface ends. */
  mount: (kind: Kind, long: string) => { ui: ReactElement; ready?: () => Promise<unknown> };
  /** Probes this surface must actually show, by kind: a probe nobody drew proves nothing. */
  expects: Record<Kind, string[]>;
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

function longProbe(kind: Kind): string {
  return kind === "unbroken" ? UNBROKEN : CATALOGUE.description;
}

const SURFACES: Surface[] = [
  {
    name: "TweakRows (TweakSetting)",
    mount: (kind, long) => {
      const setting = narrowSetting(kind);
      seed([setting], { operationError: { [setting.id]: long } });
      return {
        ui: (
          <TweakRows
            rows={[{ setting, contextLabel: long, contextIcon: <span /> }]}
          />
        ),
      };
    },
    expects: { unbroken: ["token"], catalogue: ["description", "name"] },
  },
  {
    name: "TweakListRow (Home row)",
    mount: (kind, long) => {
      const setting = narrowSetting(kind);
      seed([setting]);
      return { ui: <TweakListRow setting={setting} categoryLabel={long} /> };
    },
    expects: { unbroken: ["token"], catalogue: ["description", "name"] },
  },
  {
    name: "ActionRow",
    mount: (kind, long) => {
      const setting = narrowSetting(kind, {
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
      const setting = narrowSetting(kind, {
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
      const setting = narrowSetting(kind);
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
        ready: () => screen.findAllByText(new RegExp(long.slice(0, 20))),
      };
    },
    expects: { unbroken: ["token"], catalogue: ["description"] },
  },
  {
    name: "HomeTab groups",
    mount: (kind, long) => {
      const software = narrowSetting(kind);
      const hardware = narrowSetting(kind, {
        id: `gpu-nvidia:${software.name}` as Setting["id"],
        module: "gpu-nvidia",
        domain: "hardware",
        component: "gpu",
      });
      const game = narrowSetting(kind, {
        id: `game_config:mw4:${software.name}` as Setting["id"],
        module: "game_config",
        domain: "game",
      });
      const advisory = narrowSetting(kind, {
        id: `network:12:${software.name}` as Setting["id"],
        module: "network",
        domain: "hardware",
        component: "network_adapter",
        isReadonly: true,
        currentValue: "weak_signal",
        recommendedValue: "good",
      });
      seed([software, hardware, game, advisory]);
      return { ui: <HomeTab />, ready: () => screen.findAllByText(new RegExp(long.slice(0, 20))) };
    },
    expects: { unbroken: ["token"], catalogue: ["description"] },
  },
  {
    name: "SettingInfoTooltip",
    mount: (kind) => {
      const setting = narrowSetting(kind, { sources: [`https://example.com/${UNBROKEN}`] });
      seed([setting]);
      return {
        ui: <SettingInfoTooltip setting={setting} />,
        ready: async () => {
          await userEvent.tab();
          return screen.findAllByText(new RegExp(longProbe(kind).slice(0, 20)));
        },
      };
    },
    root: () => document.body,
    expects: { unbroken: ["token"], catalogue: ["description"] },
  },
];

function probesFor(kind: Kind): Record<string, string> {
  return kind === "unbroken"
    ? { token: UNBROKEN }
    : { name: CATALOGUE.name, description: CATALOGUE.description, effect: CATALOGUE.effect };
}

describe.each(["en", "tr"] as const)("long text at narrow widths (%s)", (locale) => {
  beforeEach(() => setLocale(locale));
  afterEach(() => setLocale("en"));

  describe.each(SURFACES)("$name", (surface) => {
    it.each(["unbroken", "catalogue"] as const)(
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
        for (const label of surface.expects[kind]) {
          expect(carriers[label], `${surface.name} never drew the ${label} probe`).toBeGreaterThan(0);
        }
        expect(violations).toEqual([]);
      },
    );
  });
});
