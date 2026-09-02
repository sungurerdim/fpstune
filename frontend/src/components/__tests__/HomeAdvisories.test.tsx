/**
 * An advisory that found something and one that found nothing are different rows.
 *
 * Home listed every `isReadonly` finding under one heading with one count, in
 * the sixth section of the page. Measured on a real machine, that heading read
 * "Advisories 6" and contained:
 *
 *   - an Ethernet link negotiated at 100 Mbps on an adapter that does 2500
 *   - five checks that found nothing wrong
 *
 * The first is the single largest ceiling loss on that box — a 25x cut to the
 * line every other network tweak is measured against — and fpstune cannot fix
 * it, because it is a cable. Which is precisely why it has to be *read*, and why
 * putting it below everything the product can do itself gets the priority
 * backwards.
 *
 * Neither half may be dropped. A clear result is the evidence the check ran: a
 * detector that finds nothing and a detector that never ran look identical once
 * you stop rendering the first.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import { HomeTab } from "../HomeTab";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

vi.mock("../HardwarePanel", () => ({ HardwarePanel: () => null }));
vi.mock("../MaintenancePanel", () => ({ MaintenancePanel: () => null }));
vi.mock("../SelfCheckNotice", () => ({ SelfCheckNotice: () => null }));

// HomeTab asks the headroom API on mount. Left unmocked, that is a real fetch
// against no server in jsdom, rejected after the test has finished; vitest
// reported it as an unhandled error in the full pre-commit run on 2026-09-02.
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

function advisory(
  id: string,
  displayName: string,
  description: string,
  isOptimized: boolean,
): Setting {
  return {
    id: id as `${string}:${string}`,
    module: id.split(":")[0],
    name: id.split(":").pop() ?? id,
    displayName,
    description,
    category: "network",
    valueType: "choice",
    choices: [],
    defaultValue: "",
    recommendedValue: "at_capability",
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
    // The whole point: fpstune detects it and cannot write it.
    isReadonly: true,
    currentValue: isOptimized ? "at_capability" : "below_capability",
    status: isOptimized ? "optimal" : "suboptimal",
    executionStatus: "idle",
    isOptimized,
    isApplicable: true,
    impactCategories: [],
  };
}

/** The real finding, in the shape the machine reported it. */
const SLOW_LINK = advisory(
  "network:19:link_capability",
  "Link Speed vs Adapter Capability (Ethernet)",
  "Compares the speed this link negotiated with the fastest speed the adapter itself supports. A gap is a cable or a switch port, not a driver setting.",
  false,
);

const RAM_FINE = advisory(
  "system:xmp_expo",
  "XMP / EXPO Profile (RAM Speed)",
  "Detects if RAM runs at rated XMP/EXPO speed or slower JEDEC default.",
  true,
);

function setStore(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map(),
    cleanupResults: {},
    categoryDetectionStatus: { core: "success" },
  } as never);
}

describe("Home separates advisories that found something", () => {
  beforeEach(() => {
    setStore([]);
  });

  it("shows a finding fpstune cannot fix under its own heading", () => {
    setStore([SLOW_LINK]);
    render(<HomeTab />);

    expect(screen.getByText("Needs your attention")).toBeInTheDocument();
    expect(
      screen.getByText("Link Speed vs Adapter Capability (Ethernet)"),
    ).toBeInTheDocument();
  });

  it("explains the finding, because the user is the one who has to act", () => {
    // Without the description the row names a problem and not what to do about
    // it — and "a cable or a switch port" is the entire actionable content.
    setStore([SLOW_LINK]);
    render(<HomeTab />);

    expect(screen.getByText(/a cable or a switch port/i)).toBeInTheDocument();
  });

  it("does not count a clear check among the ones needing attention", () => {
    // The regression: "Advisories 6" when one of the six was a real finding.
    setStore([SLOW_LINK, RAM_FINE]);
    render(<HomeTab />);

    const heading = screen.getByText("Needs your attention");
    const card = heading.closest("div")?.parentElement;
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain(
      "Link Speed vs Adapter Capability (Ethernet)",
    );
    expect(card?.textContent).not.toContain("XMP / EXPO Profile");
  });

  it("still reports the checks that found nothing", () => {
    // A detector that finds nothing must not look like a detector that is absent.
    setStore([SLOW_LINK, RAM_FINE]);
    render(<HomeTab />);

    expect(screen.getByText("Checked, nothing to change")).toBeInTheDocument();
    expect(
      screen.getByText("XMP / EXPO Profile (RAM Speed)"),
    ).toBeInTheDocument();
  });

  it("shows no attention heading when every check is clear", () => {
    setStore([RAM_FINE]);
    render(<HomeTab />);

    expect(screen.queryByText("Needs your attention")).not.toBeInTheDocument();
    expect(screen.getByText("Checked, nothing to change")).toBeInTheDocument();
  });

  it("puts the finding above the tweak lists it outweighs", () => {
    // Position is the point: the advisory names a bigger loss than anything in
    // the lists below it, and it was rendering underneath all of them.
    setStore([SLOW_LINK]);
    const { container } = render(<HomeTab />);

    const text = container.textContent ?? "";
    const advisoryAt = text.indexOf("Needs your attention");
    const hardwareAt = text.indexOf("Hardware tweaks");

    expect(advisoryAt).toBeGreaterThanOrEqual(0);
    expect(hardwareAt).toBeGreaterThanOrEqual(0);
    expect(advisoryAt).toBeLessThan(hardwareAt);
  });

  it("shows the measured numbers and the cable the ceiling needs, not the enum", () => {
    // What the machine reported: a 100 Mbps link on a 2.5 GbE adapter. The row
    // has to say exactly that and name the move — not `below_capability` and a
    // paragraph about cables in general.
    const measured: Setting = {
      ...SLOW_LINK,
      finding: { kind: "link_speed", linked_mbps: 100, ceiling_mbps: 2500 },
    };
    setStore([measured]);
    render(<HomeTab />);

    expect(screen.getByTestId("advisory-finding")).toHaveTextContent(
      "Link running at 100 Mbps; the adapter supports 2.5 Gbps.",
    );
    expect(screen.getByTestId("advisory-advice")).toHaveTextContent(
      "Use a Cat 6 or better cable",
    );
    expect(screen.queryByText(/below_capability/)).not.toBeInTheDocument();
  });

  it("never warns about a check that read nothing", () => {
    // The report: a thermal advisory shown under "needs your attention" with no
    // current value behind it. isOptimized is false whenever current does not
    // equal ideal, and a value never read equals nothing — so an unread check
    // was warning about a state nobody had measured.
    const unread: Setting = {
      ...SLOW_LINK,
      currentValue: null,
      isOptimized: false,
      detectionError: "MSAcpi_ThermalZoneTemperature WMI class not found",
    };
    setStore([unread]);
    render(<HomeTab />);

    expect(screen.queryByText("Needs your attention")).not.toBeInTheDocument();
    expect(screen.getByText("Could not be checked")).toBeInTheDocument();
    expect(
      screen.getByText(/MSAcpi_ThermalZoneTemperature WMI class not found/),
    ).toBeInTheDocument();
  });

  it("says a check read nothing even when it has no reason to give", () => {
    setStore([{ ...SLOW_LINK, currentValue: null, isOptimized: false }]);
    render(<HomeTab />);

    expect(screen.getByTestId("home-unread-advisories")).toHaveTextContent(
      "Nothing was read",
    );
    expect(screen.queryByText("Needs your attention")).not.toBeInTheDocument();
  });

  it("does not count an unread check among the clear ones either", () => {
    // "We checked and it is fine" is a claim too, and it was not checked.
    setStore([{ ...RAM_FINE, currentValue: null }]);
    render(<HomeTab />);

    expect(
      screen.queryByText("Checked, nothing to change"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Could not be checked")).toBeInTheDocument();
  });

  it("keeps an inapplicable advisory off the page entirely", () => {
    // `system:thermal_condition` reports not-applicable on a machine whose ACPI
    // exposes no thermal zone. A row that cannot mean anything is not a finding.
    const absent = { ...SLOW_LINK, isApplicable: false };
    setStore([absent]);
    render(<HomeTab />);

    expect(screen.queryByText("Needs your attention")).not.toBeInTheDocument();
  });
});
