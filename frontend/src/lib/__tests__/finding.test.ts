/**
 * An advisory's measured numbers become one concrete sentence and one move.
 *
 * The link-speed check used to log "linked at 100 Mbps but the adapter
 * supports 2500 Mbps" and show the user the word `below_capability` next to a
 * paragraph about cables in general. The numbers are the finding; the cable
 * class follows from the ceiling; and the words are the same in both locales
 * with only the phrasing changing.
 */

import { describe, it, expect, afterEach } from "vitest";
import { setLocale } from "../../i18n";
import {
  advisoryChoiceLabel,
  cableFor,
  choiceLabel,
  describeFinding,
  formatMbps,
  valueLabel,
} from "../finding";
import type { Setting } from "../../types/setting";

function advisory(overrides: Partial<Setting>): Setting {
  return {
    id: "network:19:link_capability" as `${string}:${string}`,
    domain: "software",
    module: "network",
    name: "19:link_capability",
    displayName: "Link Speed vs Adapter Capability (Ethernet)",
    description: "Compares the negotiated speed with the adapter's maximum.",
    category: "network",
    valueType: "choice",
    choices: ["at_capability", "below_capability"],
    defaultValue: "below_capability",
    recommendedValue: "at_capability",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    impactCategories: [],
    categoryOrder: 0,
    riskLevel: "safe",
    evidenceLevel: "proven",
    sources: [],
    applicableConditions: {},
    isReadonly: true,
    currentValue: "below_capability",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...overrides,
  };
}

afterEach(() => setLocale("en"));

describe("a link below the adapter's ceiling", () => {
  const slow = advisory({
    finding: { kind: "link_speed", linked_mbps: 100, ceiling_mbps: 2500 },
  });

  it("states both numbers and names the cable the ceiling needs", () => {
    const text = describeFinding(slow);
    expect(text?.summary).toBe(
      "Link running at 100 Mbps; the adapter supports 2.5 Gbps.",
    );
    expect(text?.advice).toBe(
      "Use a Cat 6 or better cable, and check the router or switch port also does 2.5 Gbps.",
    );
  });

  it("says the same in Turkish, with the Turkish decimal", () => {
    setLocale("tr");
    const text = describeFinding(slow);
    expect(text?.summary).toBe(
      "Bağlantı 100 Mbps hızında; bağdaştırıcı 2,5 Gbps destekliyor.",
    );
    expect(text?.advice).toContain("Cat 6 veya üstü kablo");
  });

  it("asks for Cat 5e when gigabit is the ceiling", () => {
    const gigabit = advisory({
      finding: { kind: "link_speed", linked_mbps: 100, ceiling_mbps: 1000 },
    });
    expect(describeFinding(gigabit)?.advice).toContain("Cat 5e or better");
    expect(describeFinding(gigabit)?.summary).toContain("supports 1 Gbps");
  });

  it("names no cable class below gigabit, where any Ethernet cable carries it", () => {
    const fast = advisory({
      finding: { kind: "link_speed", linked_mbps: 10, ceiling_mbps: 100 },
    });
    expect(describeFinding(fast)?.advice).toBe(
      "Check the cable and that the router or switch port does 100 Mbps.",
    );
  });
});

describe("a link at the ceiling", () => {
  it("still shows what it measured, and advises nothing", () => {
    const fine = advisory({
      currentValue: "at_capability",
      isOptimized: true,
      finding: { kind: "link_speed", linked_mbps: 2500, ceiling_mbps: 2500 },
    });
    expect(describeFinding(fine)).toEqual({
      summary: "Link running at 2.5 Gbps, the adapter's maximum.",
      advice: "",
    });
  });
});

describe("a Wi-Fi link", () => {
  it("reports signal, band and radio, and the move the value calls for", () => {
    const weak = advisory({
      id: "network:12:wifi_link_quality" as `${string}:${string}`,
      currentValue: "weak_signal",
      finding: {
        kind: "wifi_link",
        signal_percent: 38,
        band_ghz: 2.4,
        radio: "802.11n",
      },
    });
    const text = describeFinding(weak);
    expect(text?.summary).toBe("Signal 38% on the 2.4 GHz band (802.11n).");
    expect(text?.advice).toContain("Move closer to the router");
  });

  it("advises the band switch when the signal is fine but the band is 2.4 GHz", () => {
    const crowded = advisory({
      currentValue: "on_2_4ghz",
      finding: { kind: "wifi_link", signal_percent: 90, band_ghz: 2.4, radio: "802.11ax" },
    });
    expect(describeFinding(crowded)?.advice).toContain("5 GHz or 6 GHz");
  });

  it("says the band was not reported rather than guessing one", () => {
    const unknown = advisory({
      currentValue: "good",
      finding: { kind: "wifi_link", signal_percent: 90, band_ghz: 0, radio: "" },
    });
    expect(describeFinding(unknown)).toEqual({
      summary: "Signal 90%; band not reported.",
      advice: "",
    });
  });
});

describe("a Wi-Fi link's security", () => {
  it("names the cipher that holds the radio to 802.11g and the router setting to change", () => {
    const tkip = advisory({
      currentValue: "legacy_cipher",
      finding: {
        kind: "wifi_security",
        auth: "WPA2-Personal",
        cipher: "TKIP",
        adapter_wpa3: true,
        ap_wpa3: false,
      },
    });
    const text = describeFinding(tkip);
    expect(text?.summary).toBe(
      "WPA2-Personal with the TKIP cipher: the radio is held to 802.11g speeds.",
    );
    expect(text?.advice).toContain("WPA2 or WPA3 with AES");
  });

  it("says both ends can do WPA3 and that the speed does not change", () => {
    const wpa2 = advisory({
      currentValue: "wpa3_available",
      finding: {
        kind: "wifi_security",
        auth: "WPA2-Personal",
        cipher: "AES-CCMP",
        adapter_wpa3: true,
        ap_wpa3: true,
      },
    });
    const text = describeFinding(wpa2);
    expect(text?.summary).toBe(
      "WPA2-Personal with AES-CCMP; this adapter and the router both support WPA3.",
    );
    expect(text?.advice).toContain("Speed stays the same");
    setLocale("tr");
    expect(describeFinding(wpa2)?.advice).toContain("Hız aynı kalır");
  });

  it("reports a good link's standard and cipher with no advice", () => {
    const wpa3 = advisory({
      currentValue: "good",
      finding: {
        kind: "wifi_security",
        auth: "WPA3-Personal",
        cipher: "AES-CCMP",
        adapter_wpa3: true,
        ap_wpa3: true,
      },
    });
    expect(describeFinding(wpa3)).toEqual({
      summary: "WPA3-Personal with AES-CCMP.",
      advice: "",
    });
  });
});

describe("apps that start with Windows", () => {
  const startup = (finding: Record<string, unknown>, value = "apps_at_startup") =>
    advisory({
      id: "system:startup_apps" as `${string}:${string}`,
      choices: ["none_at_startup", "apps_at_startup"],
      currentValue: value,
      finding: { kind: "startup_apps", ...finding },
    });

  it("names what starts and where to turn it off", () => {
    expect(describeFinding(startup({ count: 2, names: ["Discord", "Steam"] }))).toEqual({
      summary: "2 apps start with Windows: Discord, Steam.",
      advice:
        "Turn off the ones you don't need in Task Manager > Startup apps; security software is not listed.",
    });
  });

  it("names the first five and counts the rest the script listed or not", () => {
    const names = ["A", "B", "C", "D", "E", "F", "G"];
    expect(describeFinding(startup({ count: 14, names }))?.summary).toBe(
      "14 apps start with Windows: A, B, C, D, E and 9 more.",
    );
  });

  it("says nothing starts, with no advice, when the list is empty", () => {
    expect(describeFinding(startup({ count: 0, names: [] }, "none_at_startup"))).toEqual({
      summary: "No third-party app starts with Windows.",
      advice: "",
    });
  });

  it("falls back to the description for a count with no names to show", () => {
    expect(describeFinding(startup({ count: 3, names: [] }))).toBeNull();
    expect(describeFinding(startup({ count: "3", names: ["A"] }))).toBeNull();
  });

  it("speaks Turkish, and labels the state in words", () => {
    setLocale("tr");
    expect(describeFinding(startup({ count: 1, names: ["OneDrive"] }))?.summary).toBe(
      "Windows ile 1 uygulama başlıyor: OneDrive.",
    );
    expect(advisoryChoiceLabel("apps_at_startup")).toBe("Başlangıçta uygulama var");
  });
});

describe("findings this module has no sentence for", () => {
  it("yield null, so the row falls back to its description, never to JSON", () => {
    expect(describeFinding(advisory({}))).toBeNull();
    expect(
      describeFinding(advisory({ finding: { kind: "something_new", x: 1 } })),
    ).toBeNull();
    expect(
      describeFinding(advisory({ finding: { kind: "link_speed", linked_mbps: "100" } })),
    ).toBeNull();
  });
});

describe("helpers", () => {
  it("formats rates the way a router's box prints them", () => {
    expect(formatMbps(100)).toBe("100 Mbps");
    expect(formatMbps(1000)).toBe("1 Gbps");
    expect(formatMbps(2500)).toBe("2.5 Gbps");
    expect(formatMbps(10000)).toBe("10 Gbps");
  });

  it("maps a ceiling to the cable class it needs", () => {
    expect(cableFor(2500)).toBe("Cat 6");
    expect(cableFor(10000)).toBe("Cat 6");
    expect(cableFor(1000)).toBe("Cat 5e");
    expect(cableFor(100)).toBe("");
  });

  it("puts an advisory's state names into words, and leaves the rest alone", () => {
    expect(advisoryChoiceLabel("below_capability")).toBe(
      "Below the adapter's maximum",
    );
    setLocale("tr");
    expect(advisoryChoiceLabel("weak_signal")).toBe("Zayıf sinyal");
    expect(advisoryChoiceLabel("High")).toBeNull();
    expect(advisoryChoiceLabel(5)).toBeNull();
  });
});

describe("a power setting whose battery rail drifted", () => {
  const drifted = advisory({
    id: "power:cpu_min_parking" as `${string}:${string}`,
    module: "power",
    isReadonly: false,
    finding: { kind: "power_dc_rail", dc_value: 100, windows_dc_default: 10 },
  });

  it("names both battery values, so a row does not show a mains number as the whole story", () => {
    const text = describeFinding(drifted);
    expect(text?.summary).toBe("On battery this reads 100; Windows' own battery value is 10.");
    expect(text?.advice).toContain("plugged-in value only");
  });

  it("says nothing when the backend sent no battery numbers", () => {
    expect(describeFinding(advisory({ finding: { kind: "power_dc_rail" } }))).toBeNull();
  });

  it("has the Turkish sentence too", () => {
    setLocale("tr");
    expect(describeFinding(drifted)?.summary).toBe(
      "Pilde bu değer 100; Windows'un kendi pil değeri 10.",
    );
  });
});

describe("a choice the backend named for this machine", () => {
  // The vendor's app calls the one-queued-frame tier "Ultra"; its older control
  // panel calls the same tier "On". The backend picks from what the driver can
  // do and sends a key, so the words follow the machine, in both languages.
  const lowLatency = advisory({
    valueType: "choice",
    isReadonly: false,
    choices: ["off", "on"],
    choiceLabels: { off: "tier.off", on: "tier.ultra" },
  });

  it("prints the named tier instead of the choice id", () => {
    expect(valueLabel(lowLatency, "on")).toBe("Ultra");
    expect(valueLabel(lowLatency, "off")).toBe("Off");
  });

  it("translates the key, so Turkish never comes from the backend", () => {
    setLocale("tr");
    expect(valueLabel(lowLatency, "off")).toBe("Kapalı");
    expect(choiceLabel(lowLatency, "on")).toBe("Ultra");
  });

  it("falls back to the id for a choice with no name or a key this build lacks", () => {
    const unknownKey = { ...lowLatency, choiceLabels: { on: "tier.does_not_exist" } };
    expect(choiceLabel(unknownKey, "on")).toBeNull();
    expect(valueLabel(unknownKey, "on")).toBe("on");
    expect(choiceLabel(lowLatency, null)).toBeNull();
    expect(valueLabel({ ...lowLatency, choiceLabels: undefined }, "off")).toBe("off");
  });
});
