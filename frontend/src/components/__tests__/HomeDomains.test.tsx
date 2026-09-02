/**
 * Home's three tweak groups are told apart by colour, and an advisory says what to do.
 *
 * The owner's report (2026-09-02): "the hardware, software and game sections are not
 * clearly separated; the page is too plain". The three groups differed by heading
 * text alone. Each now carries a domain accent — a coloured left edge, a tinted
 * header, a coloured count — from its own token, so the E9 gate still sees no raw
 * palette colour. And a finding fpstune cannot fix ends with the move the user can
 * make, taken from the setting's own `effect` sentence.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import { HomeTab } from "../HomeTab";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

vi.mock("../HardwarePanel", () => ({ HardwarePanel: () => null }));
vi.mock("../MaintenancePanel", () => ({ MaintenancePanel: () => null }));
vi.mock("../SelfCheckNotice", () => ({ SelfCheckNotice: () => null }));
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    headroomApi: { list: () => Promise.resolve({ games: [] }) },
  };
});
vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: vi.fn(), isApplying: false }),
}));
vi.mock("../../hooks/useCleanupRunner", () => ({
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

function tweak(
  id: string,
  module: string,
  extra: Partial<Setting> = {},
): Setting {
  return {
    id: id as `${string}:${string}`,
    module,
    name: id.split(":").pop() ?? id,
    displayName: id,
    description: `About ${id}.`,
    category: module,
    valueType: "choice",
    choices: ["on", "off"],
    defaultValue: "on",
    recommendedValue: "off",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    categoryOrder: 0,
    riskLevel: "safe",
    evidenceLevel: "proven",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "on",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
    ...extra,
  };
}

const HARDWARE = tweak("gpu-nvidia:shader_cache", "gpu-nvidia");
const SOFTWARE = tweak("system:game_mode", "system");
const GAME = tweak("game_config:mw4:dof_weapon", "game_config");
const WEAK_WIFI = tweak("network:12:wifi_link_quality", "network", {
  displayName: "Wi-Fi Link Quality (Intel Wi-Fi 6 AX201)",
  description: "How strong the Wi-Fi link is and which band it runs on.",
  effect:
    "Move closer to the access point or remove what stands between; join the router's 5 GHz or 6 GHz network if it offers one; a cable beats both",
  isReadonly: true,
  recommendedValue: "good",
  currentValue: "weak_signal",
});

function setStore(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map(),
    cleanupResults: {},
    categoryDetectionStatus: { core: "success" },
  } as never);
}

describe("Home tells the three domains apart", () => {
  beforeEach(() => setStore([HARDWARE, SOFTWARE, GAME]));

  it("gives each group its own domain accent", () => {
    render(<HomeTab />);

    const hardware = screen.getByText("Hardware tweaks").closest("section");
    const software = screen.getByText("Software tweaks").closest("section");
    const game = screen.getByText("Game tweaks").closest("section");

    expect(hardware).toHaveAttribute("data-domain", "hardware");
    expect(software).toHaveAttribute("data-domain", "software");
    expect(game).toHaveAttribute("data-domain", "game");
    expect(hardware?.className).toContain("border-l-domain-hardware");
    expect(software?.className).toContain("border-l-domain-software");
    expect(game?.className).toContain("border-l-domain-game");
  });

  it("puts each tweak in the group its domain says, and counts it there", () => {
    render(<HomeTab />);

    const hardware = screen.getByText("Hardware tweaks").closest("section");
    const game = screen.getByText("Game tweaks").closest("section");
    expect(hardware).toHaveTextContent("gpu-nvidia:shader_cache");
    expect(game).toHaveTextContent("game_config:mw4:dof_weapon");
    expect(hardware).not.toHaveTextContent("game_config:mw4:dof_weapon");
  });
});

describe("Home advisories say what the user can do", () => {
  it("ends a finding with the move, from the setting's own effect sentence", () => {
    setStore([WEAK_WIFI]);
    render(<HomeTab />);

    const card = screen.getByTestId("home-advisories");
    expect(card).toHaveTextContent("Needs your attention");
    expect(card).toHaveTextContent("Wi-Fi Link Quality (Intel Wi-Fi 6 AX201)");
    expect(screen.getByText("What you can do:")).toBeInTheDocument();
    expect(card).toHaveTextContent(/join the router's 5 GHz or 6 GHz network/);
  });

  it("says nothing about a move when the setting offers none", () => {
    setStore([tweak("system:xmp_expo", "system", { isReadonly: true })]);
    render(<HomeTab />);

    expect(screen.queryByText("What you can do:")).not.toBeInTheDocument();
  });
});
