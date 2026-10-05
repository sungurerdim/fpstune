import { describe, it, expect } from "vitest";
import { isSoftwareTweak } from "../tweakDomain";
import type { Setting } from "../../types/setting";

describe("isSoftwareTweak", () => {
  it("is the leftover: never a hardware or game row", () => {
    const row = (id: string, module: string) => ({ id, module }) as unknown as Setting;
    expect(isSoftwareTweak(row("network:nagle", "network"))).toBe(true);
    expect(isSoftwareTweak(row("network:nic1a2b:eee", "network"))).toBe(false);
    expect(isSoftwareTweak(row("display:mon1a2b:mode", "display"))).toBe(false);
    expect(isSoftwareTweak(row("system:xmp_expo", "system"))).toBe(false);
    expect(isSoftwareTweak(row("game_config:mw4:x", "game_config"))).toBe(false);
  });
});
