/**
 * The Hardware page has to say what is wrong loudly enough to be read.
 *
 * Reported as: status and urgency do not read, the fonts are tiny, everything is
 * collapsed, all of it is hard to see. Three separate defects sat behind that, and
 * each has a test here:
 *
 *  - **Advisories were invisible.** `isTweakListable` excludes `isReadonly` and
 *    nothing else picked them up, so Resizable BAR, GPU assignment, the fan curve
 *    and a link running under its own capability never appeared on the page about
 *    hardware — the findings most likely to cost real frames were the ones it did
 *    not mention.
 *  - **Status was grey text.** "6 not ideal" and "all ideal" were the same shape in
 *    the same colour, so which one you were looking at took reading rather than
 *    glancing.
 *  - **Everything rendered below 12px** — a mix of 9, 10 and 11px.
 *
 * The last one is guarded mechanically rather than by eye, because a stray
 * `text-[10px]` in a future edit is exactly the kind of thing review misses.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent } from "@testing-library/react";
import { render, screen, within } from "../../test/utils";
import { DeviceCard, DeviceCardCompact } from "../hardware/DeviceCard";
import { Monitor } from "lucide-react";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const applySingle = vi.fn();
const bulkRun = vi.fn();

vi.mock("../../hooks/useApplySingle", () => ({
  useApplySingle: () => ({ applySingle: (...a: unknown[]) => applySingle(...a), isPending: () => false }),
}));

vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({
    run: (...a: unknown[]) => bulkRun(...a),
    stop: vi.fn(),
    isRunning: false,
  }),
}));

function setting(overrides: Partial<Setting> & { id: string }): Setting {
  return {
    module: "gpu-hardware",
    name: "x",
    displayName: "A Tweak",
    description: "Does a thing.",
    category: "gpu",
    valueType: "choice",
    choices: [],
    defaultValue: "off",
    recommendedValue: "on",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "off",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    effect: "",
    ...overrides,
  } as Setting;
}

/** A fixable tweak sitting away from its recommended value. */
const FIXABLE = setting({
  id: "gpu-hardware:msi_mode",
  displayName: "MSI Mode",
  choices: ["disabled", "enabled"],
  currentValue: "disabled",
  recommendedValue: "enabled",
  status: "suboptimal",
});

/** Already where it should be. */
const IDEAL = setting({
  id: "gpu-hardware:already",
  displayName: "Already Fine",
  currentValue: "enabled",
  recommendedValue: "enabled",
  status: "optimal",
  isOptimized: true,
});

/** A finding only the user can act on — this is the one that was never rendered. */
const ADVISORY = setting({
  id: "gpu-hardware:resizable_bar",
  displayName: "Resizable BAR",
  currentValue: "disabled",
  recommendedValue: "enabled",
  status: "suboptimal",
  isReadonly: true,
  effect: "In BIOS, set Resizable BAR and Above 4G Decoding to Enabled.",
});

function setStore(settings: Setting[], detecting = false) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map(),
    cleanupResults: {},
    categoryDetectionStatus: detecting ? { core: "loading" } : { core: "success" },
  } as never);
}

const matchAll = () => true;

describe("DeviceCard", () => {
  beforeEach(() => {
    applySingle.mockClear();
    bulkRun.mockClear();
    setStore([]);
  });

  describe("advisories, which the page used to omit entirely", () => {
    it("lists a finding fpstune cannot write", () => {
      setStore([ADVISORY]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.getByText("Resizable BAR")).toBeInTheDocument();
    });

    it("tells the user where to change it", () => {
      setStore([ADVISORY]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.getByText(/In BIOS, set Resizable BAR/i)).toBeInTheDocument();
    });

    it("offers no Fix button for something no button can fix", () => {
      setStore([ADVISORY]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.queryByRole("button", { name: /^Fix/i })).not.toBeInTheDocument();
    });

    it("counts advisories apart from the fixable ones", () => {
      // A single count spanning both would make "Fix all" a claim about settings it
      // will not touch.
      setStore([FIXABLE, ADVISORY]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.getByText("1 to apply")).toBeInTheDocument();
      expect(screen.getByText("1 need you")).toBeInTheDocument();
    });

    it("leaves advisories out of the device's Apply", () => {
      setStore([FIXABLE, ADVISORY]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      fireEvent.click(screen.getByRole("button", { name: "Apply 1 tweaks: GPU" }));
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Apply" }));

      expect(bulkRun).toHaveBeenCalledTimes(1);
      expect(bulkRun).toHaveBeenCalledWith("apply", ["gpu-hardware:msi_mode"]);
    });

    it("asks before a device-wide Windows default, and names the count", () => {
      setStore([FIXABLE, ADVISORY]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      fireEvent.click(
        screen.getByRole("button", { name: "Return 1 settings to the Windows default: GPU" }),
      );

      expect(bulkRun).not.toHaveBeenCalled();
      expect(screen.getByRole("dialog")).toHaveTextContent(
        "1 settings will return to Windows defaults.",
      );
    });

    it("offers Undo only when the device has a recorded original", () => {
      setStore([FIXABLE]);
      const { unmount } = render(
        <DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />,
      );
      expect(screen.queryByRole("button", { name: /^Undo/ })).not.toBeInTheDocument();
      unmount();

      setStore([setting({ ...FIXABLE, originalValue: "enabled" })]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);
      expect(screen.getByRole("button", { name: "Undo 1 tweaks: GPU" })).toBeInTheDocument();
    });

    it("does not count an advisory that is already at its recommended value", () => {
      const passed = setting({
        ...ADVISORY,
        id: "gpu-hardware:rebar_ok",
        status: "optimal",
        isReadonly: true,
        isOptimized: true,
      });
      setStore([FIXABLE, passed]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.queryByText(/need you/i)).not.toBeInTheDocument();
    });
  });

  describe("status has to read at a glance", () => {
    it("states how many need fixing", () => {
      setStore([FIXABLE, IDEAL]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.getByText("1 to apply")).toBeInTheDocument();
    });

    it("says so plainly when nothing needs doing", () => {
      setStore([IDEAL]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.getByText("Ideal")).toBeInTheDocument();
    });

    it("shows the problem without anything being expanded first", () => {
      // "Everything is collapsed" was half the complaint. A suboptimal row is
      // visible on first render; only the already-ideal ones are behind the toggle.
      setStore([FIXABLE, IDEAL]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.getByText("MSI Mode")).toBeInTheDocument();
      expect(screen.queryByText("Already Fine")).not.toBeInTheDocument();
    });

    it("reveals the settled ones on request", () => {
      setStore([FIXABLE, IDEAL]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      fireEvent.click(screen.getByRole("button", { name: /show 1 already ideal/i }));

      expect(screen.getByText("Already Fine")).toBeInTheDocument();
    });

    it("does not imply a device is clean before anything has been read", () => {
      setStore([], true);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.getByText(/Reading tweaks/i)).toBeInTheDocument();
      expect(screen.queryByText(/ideal/i)).not.toBeInTheDocument();
    });
  });

  describe("nothing renders below 12px", () => {
    // The page mixed text-[9px], text-[10px] and text-[11px]. Asserting on the
    // rendered class names catches a reintroduction in any of these rows, which is
    // not something a screenshot review reliably notices.
    it.each([
      ["a fixable tweak", [FIXABLE]],
      ["an advisory", [ADVISORY]],
      ["a settled device", [IDEAL]],
    ])("keeps %s above the readable floor", (_label, settings) => {
      setStore(settings as Setting[]);
      const { container } = render(
        <DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />,
      );

      const tiny = Array.from(container.querySelectorAll<HTMLElement>("[class]")).filter(
        (el) => /text-\[(?:[0-9]|10|11)px\]/.test(el.className),
      );

      expect(tiny.map((el) => el.className)).toEqual([]);
    });
  });

  describe("the fix still works", () => {
    it("applies one tweak with its recommended value", () => {
      setStore([FIXABLE]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      // The shared row, the same one Software and Games use — not a private copy.
      fireEvent.click(screen.getByRole("switch", { name: "MSI Mode" }));

      expect(applySingle).toHaveBeenCalledWith(
        expect.objectContaining({ id: "gpu-hardware:msi_mode" }),
        "enabled",
      );
    });
  });

  describe("the card itself", () => {
    it("is a labelled region named after the device, edge tone said in words too", () => {
      setStore([FIXABLE]);
      render(<DeviceCard deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      const card = screen.getByRole("region", { name: "GPU" });
      expect(card).toHaveAttribute("data-tone", "attention");
      // Colour is never the only signal.
      expect(within(card).getByText("1 to apply")).toBeInTheDocument();
    });

    it("draws a device with nothing to tune grey, and says so", () => {
      setStore([]);
      render(<DeviceCard deviceKey="drive-C" icon={Monitor} title="C: Example SSD" />);

      expect(screen.getByRole("region", { name: "C: Example SSD" })).toHaveAttribute(
        "data-tone",
        "none",
      );
      expect(screen.getByText("Nothing to tune on this device")).toBeInTheDocument();
    });

    it("draws no card for a component's machine-wide tweaks when it has none", () => {
      setStore([]);
      render(
        <DeviceCard deviceKey="buses" icon={Monitor} title="USB & PCIe" match={matchAll} sharedOnly />,
      );

      expect(screen.queryByRole("region")).not.toBeInTheDocument();
    });
  });

  describe("Home's compact card", () => {
    it("is absent when the device has nothing to apply", () => {
      setStore([IDEAL]);
      render(<DeviceCardCompact deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.queryByRole("region")).not.toBeInTheDocument();
    });

    it("offers one Apply for the device and nothing else", () => {
      setStore([setting({ ...FIXABLE, originalValue: "enabled" })]);
      render(<DeviceCardCompact deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      expect(screen.getByRole("button", { name: "Apply 1 tweaks: GPU" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^Undo/ })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Open GPU on the Hardware page" })).toBeInTheDocument();
    });

    it("opens the Hardware page", async () => {
      setStore([FIXABLE]);
      useStore.setState({ activeTab: "home" } as never);
      render(<DeviceCardCompact deviceKey="gpu-0" icon={Monitor} title="GPU" match={matchAll} />);

      fireEvent.click(screen.getByRole("button", { name: "Open GPU on the Hardware page" }));
      expect(useStore.getState().activeTab).toBe("hardware");
    });
  });
});
