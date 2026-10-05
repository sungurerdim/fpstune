import { describe, it, expect } from "vitest";
import { isComponentTweak, isGameTweak, isHardwareTweak, isSoftwareTweak } from "../tweakDomain";
import type { Setting } from "../../types/setting";

const row = (id: string, domain: Setting["domain"], component?: Setting["component"]) =>
  ({ id, module: id.split(":")[0], domain, component }) as unknown as Setting;

describe("tweak domain", () => {
  it("follows the backend's domain, not the id: a powercfg key can be hardware", () => {
    const pcie = row("power:pcie_link_state", "hardware", "pcie");
    expect(isHardwareTweak(pcie)).toBe(true);
    expect(isSoftwareTweak(pcie)).toBe(false);
    expect(isComponentTweak(pcie, "pcie")).toBe(true);
  });

  it("partitions: each row answers true to exactly one predicate", () => {
    for (const s of [
      row("network:nagle", "software"),
      row("network:nic1a2b:eee", "hardware", "network_adapter"),
      row("game_config:mw4:x", "game"),
    ]) {
      const hits = [isGameTweak(s), isHardwareTweak(s), isSoftwareTweak(s)].filter(Boolean);
      expect(hits).toHaveLength(1);
    }
  });
});
