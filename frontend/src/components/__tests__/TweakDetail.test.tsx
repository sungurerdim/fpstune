/**
 * TweakDetail: everything the one-line row leaves out, behind its (i).
 *
 * Each case names the way a detail panel goes wrong that a screenshot would not
 * show: a disclosure that does not say it is open, a panel a keyboard user can
 * enter but cannot leave without losing their place, a Reset offered when there
 * is nothing to write back, a default that does not say whose default it is.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setLocale } from "../../i18n";
import {
  CATALOGUE,
  UNBROKEN,
  advisoryProbes,
  narrowAdvisory,
  narrowReport,
  narrowSetting,
} from "../../test/narrow";
import type { Setting } from "../../types/setting";
import { TweakDetail } from "../TweakDetail";

function makeSetting(overrides: Partial<Setting> = {}): Setting {
  return {
    id: "network:nagle_algorithm" as Setting["id"],
    domain: "software",
    module: "network",
    name: "nagle_algorithm",
    displayName: "Nagle's algorithm",
    description: "Batches small packets before sending them. It adds delay to games.",
    category: "network",
    valueType: "choice",
    choices: ["enabled", "disabled"],
    defaultValue: "enabled",
    recommendedValue: "disabled",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "Enabled: small packets wait for a full buffer",
    recommendedImpact: "Disabled: small packets leave at once",
    effect: "Lowers network latency in online games",
    impactScores: { latency_ms: -5 },
    impactCategories: ["latency"],
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "proven",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    choiceLabels: { enabled: "tier.on", disabled: "tier.off" },
    currentValue: "enabled",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...overrides,
  };
}

function renderDetail(
  setting: Setting,
  props: { onReset?: () => void; error?: string; busy?: boolean } = {},
) {
  const onReset = props.onReset ?? vi.fn();
  const onApply = vi.fn();
  const view = render(
    <TweakDetail setting={setting} onReset={onReset} error={props.error} busy={props.busy}>
      {(trigger) => (
        <div>
          <button type="button" onClick={onApply}>
            Apply
          </button>
          {trigger}
        </div>
      )}
    </TweakDetail>,
  );
  return { onReset, onApply, ...view };
}

// The (i) is named "Information about X" / "X hakkında bilgi": found by what it
// is (the one disclosure button), so the same query serves both languages.
const trigger = () =>
  screen.getByRole("button", { name: /^Information about|hakkında bilgi$/ });
const panel = () => screen.queryByRole("region");
const resetButton = () => screen.queryByRole("button", { name: /^Reset .* to default/ });

/** Optimized and away from stock: the one state in which Reset has something to write. */
const OPTIMIZED: Partial<Setting> = { currentValue: "disabled", isOptimized: true };

afterEach(() => setLocale("en"));

describe("the (i) says whether it is open", () => {
  it("starts closed: aria-expanded false, no panel, nothing for aria-controls to point at", () => {
    renderDetail(makeSetting());

    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(trigger()).not.toHaveAttribute("aria-controls");
    expect(panel()).toBeNull();
  });

  it("toggles aria-expanded with each press, and points at the panel while it is open", async () => {
    renderDetail(makeSetting());

    await userEvent.click(trigger());
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    expect(panel()).toBeInTheDocument();
    expect(trigger().getAttribute("aria-controls")).toBe(panel()!.id);

    await userEvent.click(trigger());
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(panel()).toBeNull();
  });

  it("opens from the keyboard", async () => {
    renderDetail(makeSetting());

    trigger().focus();
    await userEvent.keyboard("{Enter}");

    expect(trigger()).toHaveAttribute("aria-expanded", "true");
  });

  it("names the panel after the setting, so a list of panels is not a list of 'region'", async () => {
    renderDetail(makeSetting());
    await userEvent.click(trigger());

    expect(panel()).toHaveAccessibleName("Information about Nagle's algorithm");
  });

  it("is only the (i) when the row gives it no line to sit in", () => {
    render(<TweakDetail setting={makeSetting()} onReset={vi.fn()} />);

    expect(trigger()).toBeInTheDocument();
  });
});

describe("Escape closes it and the keyboard user keeps their place", () => {
  it("closes from a control inside the panel and puts focus back on the (i)", async () => {
    renderDetail(makeSetting(OPTIMIZED));
    await userEvent.click(trigger());

    // Focus the Reset button inside the panel, then leave: the button is
    // unmounted with the panel, which is exactly when focus would be lost.
    resetButton()!.focus();
    expect(resetButton()).toHaveFocus();
    await userEvent.keyboard("{Escape}");

    expect(panel()).toBeNull();
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(trigger()).toHaveFocus();
  });

  it("closes from the row's own Apply too, not only from inside the panel", async () => {
    renderDetail(makeSetting());
    await userEvent.click(trigger());

    screen.getByRole("button", { name: "Apply" }).focus();
    await userEvent.keyboard("{Escape}");

    expect(panel()).toBeNull();
    expect(trigger()).toHaveFocus();
  });

  it("keeps the Escape to itself while open, so a dialog around the list stays open", async () => {
    const outer = vi.fn();
    render(
      <div onKeyDown={outer}>
        <TweakDetail setting={makeSetting()} onReset={vi.fn()} />
      </div>,
    );
    await userEvent.click(trigger());

    await userEvent.keyboard("{Escape}");

    expect(outer).not.toHaveBeenCalled();
  });

  it("lets Escape through when nothing is open, so the dialog around the list can close", async () => {
    const outer = vi.fn();
    render(
      <div onKeyDown={outer}>
        <TweakDetail setting={makeSetting()} onReset={vi.fn()} />
      </div>,
    );
    trigger().focus();

    await userEvent.keyboard("{Escape}");

    expect(outer).toHaveBeenCalledTimes(1);
  });
});

describe("what it says", () => {
  it("gives the description, the effect and what the setting claims, in its own words", async () => {
    renderDetail(makeSetting());
    await userEvent.click(trigger());
    const detail = within(panel()!);

    expect(detail.getByText(/Batches small packets/)).toBeInTheDocument();
    expect(detail.getByText("Lowers network latency in online games")).toBeInTheDocument();
    expect(detail.getByText("latency ms:")).toBeInTheDocument();
    expect(detail.getByText("-5")).toBeInTheDocument();
    expect(detail.getByText("Latency")).toBeInTheDocument();
  });

  it("says what the machine is on and what is recommended, by value", async () => {
    renderDetail(makeSetting());
    await userEvent.click(trigger());

    expect(panel()).toHaveTextContent("Current: On · Recommended: Off");
  });

  it("shows the risk warning behind a RISK chip when the risk is advanced, a NOTE otherwise", async () => {
    const { unmount } = renderDetail(
      makeSetting({ riskLevel: "advanced", riskWarning: "Can drop the connection on some routers." }),
    );
    await userEvent.click(trigger());
    expect(screen.getByTestId("detail-risk-chip")).toHaveTextContent("RISK");
    expect(panel()).toHaveTextContent("Can drop the connection on some routers.");
    unmount();

    renderDetail(makeSetting({ riskLevel: "moderate", riskWarning: "Some games ignore it." }));
    await userEvent.click(trigger());
    expect(screen.getByTestId("detail-risk-chip")).toHaveTextContent("NOTE");
  });

  it("states what a visible-quality setting costs, and a required restart", async () => {
    renderDetail(
      makeSetting({ perceptibleCost: "Shadows around corners turn off.", requiresReboot: true }),
    );
    await userEvent.click(trigger());

    expect(panel()).toHaveTextContent("Cost: Shadows around corners turn off.");
    expect(panel()).toHaveTextContent("Requires system restart");
  });

  it("links each source by its host, never the raw URL as the label", async () => {
    renderDetail(makeSetting({ sources: ["https://www.example.com/guide/nagle"] }));
    await userEvent.click(trigger());

    const link = within(panel()!).getByRole("link", { name: "example.com" });
    expect(link).toHaveAttribute("href", "https://www.example.com/guide/nagle");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("does not throw on a source that is not a URL", async () => {
    renderDetail(makeSetting({ sources: ["not a url"] }));
    await userEvent.click(trigger());

    expect(within(panel()!).getByRole("link", { name: "not a url" })).toBeInTheDocument();
  });

  it("gives the reason a setting does not apply, and a failed run's reason", async () => {
    renderDetail(makeSetting({ isApplicable: false, applicableReason: "No Wi-Fi adapter was found." }), {
      error: "Access is denied.",
    });
    await userEvent.click(trigger());

    expect(panel()).toHaveTextContent("No Wi-Fi adapter was found.");
    expect(panel()).toHaveTextContent("Access is denied.");
  });

  it("writes an advisory's measured finding in the machine's numbers", async () => {
    renderDetail(
      makeSetting({
        isReadonly: true,
        finding: { kind: "link_speed", linked_mbps: 100, ceiling_mbps: 2500 },
        effect: "Replace the cable.",
        valueType: "choice",
        choices: ["at_capability", "below_capability"],
        currentValue: "below_capability",
        recommendedValue: "at_capability",
        defaultValue: "below_capability",
        choiceLabels: undefined,
      }),
    );
    await userEvent.click(trigger());

    expect(panel()).toHaveTextContent("Link running at 100 Mbps; the adapter supports 2.5 Gbps.");
    // A readonly row has no Apply: its effect is the instruction, and says so.
    expect(panel()).toHaveTextContent("How to change: Replace the cable.");
    expect(resetButton()).toBeNull();
  });
});

describe("the way back: the default, whose it is, and Reset to default", () => {
  it.each([
    ["software", "Windows default: On"],
    ["hardware", "Driver default: On"],
    ["game", "Game default: On"],
  ] as const)("names the %s default and its value", async (domain, expected) => {
    renderDetail(makeSetting({ domain }));
    await userEvent.click(trigger());

    expect(panel()).toHaveTextContent(expected);
  });

  it("offers Reset to default, which names the default it writes, and calls back once", async () => {
    const { onReset } = renderDetail(makeSetting(OPTIMIZED));
    await userEvent.click(trigger());

    expect(resetButton()).toHaveTextContent("Reset to default");
    expect(resetButton()).toHaveAccessibleName(
      "Reset Nagle's algorithm to default: Windows default (On)",
    );
    await userEvent.click(resetButton()!);

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("omits Reset when the setting has no default of its own — none is invented", async () => {
    renderDetail(makeSetting({ defaultValue: null }));
    await userEvent.click(trigger());

    expect(resetButton()).toBeNull();
    expect(panel()).not.toHaveTextContent("Windows default");
  });

  it("omits Reset when the machine is already at the default, but still says what it is", async () => {
    renderDetail(makeSetting({ currentValue: "enabled", defaultValue: "enabled" }));
    await userEvent.click(trigger());

    expect(resetButton()).toBeNull();
    expect(panel()).toHaveTextContent("Windows default: On");
  });

  it("disables Reset while a run on this row is going, so it cannot be pressed twice", async () => {
    renderDetail(makeSetting(OPTIMIZED), { busy: true });
    await userEvent.click(trigger());

    expect(resetButton()).toBeDisabled();
  });
});

describe("long text stays inside the panel, in both languages", () => {
  const KINDS = ["unbroken", "catalogue"] as const;

  it.each(["en", "tr"] as const)("keeps an unbroken token and the longest real copy in frame (%s)", async (locale) => {
    setLocale(locale);
    for (const kind of KINDS) {
      const setting = narrowSetting(kind, { riskLevel: "advanced", riskWarning: kind === "unbroken" ? UNBROKEN : CATALOGUE.description });
      const { container, unmount } = renderDetail(setting, { error: kind === "unbroken" ? UNBROKEN : CATALOGUE.description });
      await userEvent.click(trigger());

      const probes: Record<string, string> =
        kind === "unbroken"
          ? { token: UNBROKEN }
          : { name: CATALOGUE.name, description: CATALOGUE.description, effect: CATALOGUE.effect };
      const { violations, carriers } = narrowReport(container, probes);

      expect(Object.values(carriers).every((n) => n > 0), `${kind} probes drawn: ${JSON.stringify(carriers)}`).toBe(true);
      expect(violations).toEqual([]);
      unmount();
    }
  });

  it.each(["en", "tr"] as const)("keeps an advisory's state and instruction in frame (%s)", async (locale) => {
    setLocale(locale);
    const setting = narrowAdvisory();
    const { container } = renderDetail(setting);
    await userEvent.click(trigger());

    const probes = advisoryProbes(setting);
    const { violations, carriers } = narrowReport(container, {
      advisoryName: probes.advisoryName,
      advisoryHint: probes.advisoryHint,
    });

    expect(carriers.advisoryName).toBeGreaterThan(0);
    expect(carriers.advisoryHint).toBeGreaterThan(0);
    expect(violations).toEqual([]);
  });
});

describe("the case for changing follows whether there is anything to change", () => {
  // Verbosity follows actionability: the effect and the "as it is now" line are
  // the argument for applying, and a setting already right is not asking for one.
  it("drops the effect and the as-it-is line once the setting is optimized, and keeps what is true now", async () => {
    renderDetail(makeSetting({ ...OPTIMIZED, effect: "Lowers network latency in online games" }));
    await userEvent.click(trigger());
    const detail = within(panel()!);

    expect(detail.queryByText("Lowers network latency in online games")).not.toBeInTheDocument();
    expect(detail.queryByText("Enabled: small packets wait for a full buffer")).not.toBeInTheDocument();
    // The recommended line is the one that is true right now.
    expect(detail.getByText("Disabled: small packets leave at once")).toBeInTheDocument();
  });

  it("keeps the whole case while the setting still needs applying", async () => {
    renderDetail(makeSetting({ effect: "Lowers network latency in online games" }));
    await userEvent.click(trigger());
    const detail = within(panel()!);

    expect(detail.getByText("Lowers network latency in online games")).toBeInTheDocument();
    expect(detail.getByText("Enabled: small packets wait for a full buffer")).toBeInTheDocument();
    expect(detail.getByText("Disabled: small packets leave at once")).toBeInTheDocument();
  });

  it("keeps the how-to on an advisory even when it reads OK", async () => {
    // An advisory has no Apply, so this line is the only place that tells the
    // user what to do about it.
    renderDetail(
      makeSetting({
        ...OPTIMIZED,
        isReadonly: true,
        effect: "Enable Resizable BAR in the UEFI setup",
      }),
    );
    await userEvent.click(trigger());
    const detail = within(panel()!);

    expect(detail.getByText("How to change:")).toBeInTheDocument();
    expect(detail.getByText("Enable Resizable BAR in the UEFI setup")).toBeInTheDocument();
  });
});
