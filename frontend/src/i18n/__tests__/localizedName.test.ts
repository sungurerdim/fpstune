/**
 * A per-adapter row keeps its adapter in every locale.
 *
 * The Turkish table is keyed per setting (`network:*:power_management`), so its
 * name alone made a Wi-Fi and an Ethernet row identical on Home.
 */

import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "../index";
import { localizedName } from "../settings";
import type { Setting } from "../../types/setting";

function row(id: string, shortName: string, subject?: string): Setting {
  return { id, displayName: shortName, shortName, subject } as unknown as Setting;
}

afterEach(() => setLocale("en"));

describe("localizedName", () => {
  it("tells two adapters' copies of one setting apart in Turkish", () => {
    setLocale("tr");
    const wifi = row("network:nic3f09a1c2d4:power_management", "Adapter power saving (Wi-Fi)", "Wi-Fi");
    const lan = row("network:nic7b21e0aa95:power_management", "Adapter power saving (Ethernet)", "Ethernet");
    expect(localizedName(wifi)).toBe("Bağdaştırıcı güç tasarrufu (Wi-Fi)");
    expect(localizedName(lan)).toBe("Bağdaştırıcı güç tasarrufu (Ethernet)");
  });

  it("adds no qualifier to a machine-wide setting", () => {
    setLocale("tr");
    expect(localizedName(row("power:wlan_power_saving", "Wi-Fi power saving"))).toBe(
      "Wi-Fi güç tasarrufu",
    );
  });

  it("leaves the English name, which already carries the adapter, untouched", () => {
    const wifi = row("network:nic3f09a1c2d4:power_management", "Adapter power saving (Wi-Fi)", "Wi-Fi");
    expect(localizedName(wifi)).toBe("Adapter power saving (Wi-Fi)");
  });
});
