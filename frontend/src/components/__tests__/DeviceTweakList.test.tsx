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
import { DeviceTweakList } from "../hardware/DeviceTweakList";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const applySingle = vi.fn();
const bulkApply = vi.fn();

vi.mock("../../hooks/useApplySingle", () => ({
  useApplySingle: () => ({ applySingle: (...a: unknown[]) => applySingle(...a), isPending: () => false }),
}));

vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: (...a: unknown[]) => bulkApply(...a), isApplying: false }),
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

describe("DeviceTweakList", () => {
  beforeEach(() => {
    applySingle.mockClear();
    bulkApply.mockClear();
    setStore([]);
  });

  describe("advisories, which the page used to omit entirely", () => {
    it("lists a finding fpstune cannot write", () => {
      setStore([ADVISORY]);
      render(<DeviceTweakList match={matchAll} />);

      expect(screen.getByText("Resizable BAR")).toBeInTheDocument();
    });

    it("tells the user where to change it", () => {
      setStore([ADVISORY]);
      render(<DeviceTweakList match={matchAll} />);

      expect(screen.getByText(/In BIOS, set Resizable BAR/i)).toBeInTheDocument();
    });

    it("offers no Fix button for something no button can fix", () => {
      setStore([ADVISORY]);
      render(<DeviceTweakList match={matchAll} />);

      expect(screen.queryByRole("button", { name: /^Fix/i })).not.toBeInTheDocument();
    });

    it("counts advisories apart from the fixable ones", () => {
      // A single count spanning both would make "Fix all" a claim about settings it
      // will not touch.
      setStore([FIXABLE, ADVISORY]);
      render(<DeviceTweakList match={matchAll} />);

      expect(screen.getByText("1 to fix")).toBeInTheDocument();
      expect(screen.getByText("1 need you")).toBeInTheDocument();
    });

    it("leaves advisories out of Fix all", () => {
      setStore([FIXABLE, ADVISORY]);
      render(<DeviceTweakList match={matchAll} />);

      fireEvent.click(screen.getByRole("button", { name: /fix all/i }));

      expect(bulkApply).toHaveBeenCalledTimes(1);
      expect(bulkApply).toHaveBeenCalledWith({ "gpu-hardware:msi_mode": "enabled" });
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
      render(<DeviceTweakList match={matchAll} />);

      expect(screen.queryByText(/need you/i)).not.toBeInTheDocument();
    });
  });

  describe("status has to read at a glance", () => {
    it("states how many need fixing", () => {
      setStore([FIXABLE, IDEAL]);
      render(<DeviceTweakList match={matchAll} />);

      expect(screen.getByText("1 to fix")).toBeInTheDocument();
    });

    it("says so plainly when nothing needs doing", () => {
      setStore([IDEAL]);
      render(<DeviceTweakList match={matchAll} />);

      expect(screen.getByText("All 1 ideal")).toBeInTheDocument();
    });

    it("shows the problem without anything being expanded first", () => {
      // "Everything is collapsed" was half the complaint. A suboptimal row is
      // visible on first render; only the already-ideal ones are behind the toggle.
      setStore([FIXABLE, IDEAL]);
      render(<DeviceTweakList match={matchAll} />);

      expect(screen.getByText("MSI Mode")).toBeInTheDocument();
      expect(screen.queryByText("Already Fine")).not.toBeInTheDocument();
    });

    it("reveals the settled ones on request", () => {
      setStore([FIXABLE, IDEAL]);
      render(<DeviceTweakList match={matchAll} />);

      fireEvent.click(screen.getByRole("button", { name: /show tweaks already ideal/i }));

      expect(screen.getByText("Already Fine")).toBeInTheDocument();
    });

    it("does not imply a device is clean before anything has been read", () => {
      setStore([], true);
      render(<DeviceTweakList match={matchAll} />);

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
      const { container } = render(<DeviceTweakList match={matchAll} />);

      const tiny = Array.from(container.querySelectorAll<HTMLElement>("[class]")).filter(
        (el) => /text-\[(?:[0-9]|10|11)px\]/.test(el.className),
      );

      expect(tiny.map((el) => el.className)).toEqual([]);
    });
  });

  describe("the fix still works", () => {
    it("applies one tweak with its recommended value", () => {
      setStore([FIXABLE]);
      render(<DeviceTweakList match={matchAll} />);

      const row = screen.getByText("MSI Mode").parentElement as HTMLElement;
      fireEvent.click(within(row).getByRole("button", { name: /apply msi mode/i }));

      expect(applySingle).toHaveBeenCalledWith(
        expect.objectContaining({ id: "gpu-hardware:msi_mode" }),
        "enabled",
      );
    });
  });
});
