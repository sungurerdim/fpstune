/**
 * The adapter switch used to be named after the action it would perform next
 * ("Disable adapter hardware" / "Enable adapter hardware"), or after the reason
 * it was inert. With role="switch" the on/off half belongs in aria-checked, and
 * a name that changes with the state makes the control a screen-reader user
 * just toggled unfindable under its previous name. The stable subject — the
 * adapter Windows reported — is the name.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "../../test/utils";
import { NetworkAdapterCard } from "../hardware/NetworkAdapterCard";
import type { NetworkAdapterInfo } from "../../lib/api";

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: { refreshNetworkAdapters: vi.fn().mockResolvedValue([]) },
}));

// The per-adapter tweak list reads the store; these tests are about the
// adapter switch, so it stays out of the tree.
vi.mock("../hardware/DeviceTweakList", () => ({
  DeviceTweakList: () => null,
}));

function adapter(
  overrides: Partial<NetworkAdapterInfo> = {},
): NetworkAdapterInfo {
  return {
    name: "Ethernet",
    description: "Intel(R) Ethernet Connection I219-V",
    adapter_type: "Ethernet",
    status: "Up",
    is_enabled: true,
    is_connected: true,
    dns_servers: [],
    interface_index: 12,
    instance_id: "PCI\\VEN_8086&DEV_15BC\\3&11583659&0&FE",
    ...overrides,
  };
}

describe("the adapter switch is named after the adapter", () => {
  it("is findable by the adapter's own name", () => {
    render(<NetworkAdapterCard adapter={adapter()} />);

    expect(
      screen.getByRole("switch", { name: "Ethernet" }),
    ).toBeInTheDocument();
  });

  it("keeps the same name across a state flip; only aria-checked moves", () => {
    const { rerender } = render(
      <NetworkAdapterCard adapter={adapter({ is_enabled: true })} />,
    );

    expect(screen.getByRole("switch", { name: "Ethernet" })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    rerender(<NetworkAdapterCard adapter={adapter({ is_enabled: false })} />);

    expect(screen.getByRole("switch", { name: "Ethernet" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("still says which adapter it is when the switch is inert", () => {
    // A phantom adapter's switch is disabled, but "which adapter" must survive:
    // naming it after the reason left an anonymous control among named ones.
    render(
      <NetworkAdapterCard
        adapter={adapter({ status: "NotConnected", is_enabled: false })}
      />,
    );

    const toggle = screen.getByRole("switch", { name: "Ethernet" });
    expect(toggle).toBeDisabled();
    expect(toggle).toHaveAttribute("aria-checked", "false");
  });
});

describe("an inert switch says why it is inert", () => {
  it("badges an adapter Windows gave no identifier for", () => {
    // Moving the title to the adapter's name took the reason with it, and the
    // reason had nowhere else to go: an enable/disable call needs either an
    // instance id or an interface index, and this adapter reported neither. The
    // switch is disabled and, until this badge, nothing said so in any form a
    // reader or a sighted user could reach.
    render(
      <NetworkAdapterCard
        adapter={adapter({ instance_id: undefined, interface_index: null })}
      />,
    );

    expect(screen.getByRole("switch", { name: "Ethernet" })).toBeDisabled();
    expect(screen.getByText("Not controllable")).toBeInTheDocument();
  });

  it("leaves a phantom adapter to its own badge", () => {
    // "Not Connected" already answers the question for that case; two badges
    // saying the same thing is noise, not an explanation.
    render(
      <NetworkAdapterCard
        adapter={adapter({ status: "NotConnected", is_enabled: false })}
      />,
    );

    expect(screen.getByText("Not Connected")).toBeInTheDocument();
    expect(screen.queryByText("Not controllable")).not.toBeInTheDocument();
  });

  it("says nothing extra about an adapter that can be controlled", () => {
    render(<NetworkAdapterCard adapter={adapter()} />);

    expect(screen.queryByText("Not controllable")).not.toBeInTheDocument();
  });
});

describe("the reason travels with the switch, not merely beside it", () => {
  /** The text `aria-describedby` actually resolves to, in id order. */
  function describedText(control: HTMLElement): string[] {
    const ids = control.getAttribute("aria-describedby")?.split(" ") ?? [];
    return ids.map((id) => document.getElementById(id)?.textContent ?? "");
  }

  it("points a no-identifier switch at its own badge", () => {
    // The badge sat next to the switch and nothing linked them, so a reader
    // landing on the disabled control heard the adapter's name and no reason —
    // the explanation arrived only after the thing it explained.
    render(
      <NetworkAdapterCard
        adapter={adapter({ instance_id: undefined, interface_index: null })}
      />,
    );

    const toggle = screen.getByRole("switch", { name: "Ethernet" });
    expect(toggle).toHaveAttribute("aria-describedby");
    expect(describedText(toggle)).toEqual(["Not controllable"]);
  });

  it("points a phantom switch at its own badge", () => {
    render(
      <NetworkAdapterCard
        adapter={adapter({ status: "NotConnected", is_enabled: false })}
      />,
    );

    const toggle = screen.getByRole("switch", { name: "Ethernet" });
    expect(toggle).toHaveAttribute("aria-describedby");
    expect(describedText(toggle)).toEqual(["Not Connected"]);
  });

  it("describes a controllable switch with nothing at all", () => {
    // "Connected" is a status, not a reason the control is inert; pointing at
    // it would make every working switch announce a description it does not
    // need.
    render(<NetworkAdapterCard adapter={adapter()} />);

    expect(screen.getByRole("switch", { name: "Ethernet" })).not.toHaveAttribute(
      "aria-describedby",
    );
  });

  it("gives each card its own reason id", () => {
    // Many adapter cards render at once. A constant id would make every card's
    // switch resolve to the first card's badge, and the second adapter would be
    // described by the first one's reason.
    render(
      <>
        <NetworkAdapterCard
          adapter={adapter({
            name: "Ethernet",
            instance_id: undefined,
            interface_index: null,
          })}
        />
        <NetworkAdapterCard
          adapter={adapter({
            name: "Wi-Fi",
            adapter_type: "WiFi",
            instance_id: undefined,
            interface_index: null,
          })}
        />
      </>,
    );

    const first = screen
      .getByRole("switch", { name: "Ethernet" })
      .getAttribute("aria-describedby");
    const second = screen
      .getByRole("switch", { name: "Wi-Fi" })
      .getAttribute("aria-describedby");

    expect(first).toBeTruthy();
    expect(second).toBeTruthy();
    expect(first).not.toBe(second);
  });
});
