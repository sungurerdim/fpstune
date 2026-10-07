import { describe, it, expect } from "vitest";
import {
  categoryGroups,
  gameGroups,
  isComponentTweak,
  isGameTweak,
  isHardwareTweak,
  isSoftwareTweak,
  partitionByDomain,
} from "../tweakDomain";
import type { CategoryMetadata, Setting } from "../../types/setting";

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

describe("partitionByDomain", () => {
  it("puts every row in exactly one list, whatever its id says", () => {
    const rows = [
      row("network:nagle", "software"),
      row("power:pcie_link_state", "hardware", "pcie"),
      row("network:nic1a2b:eee", "hardware", "network_adapter"),
      row("game_config:mw4:shadow_quality", "game"),
    ];
    const { software, hardware, game } = partitionByDomain(rows);

    expect(software.map((s) => s.id)).toEqual(["network:nagle"]);
    expect(hardware.map((s) => s.id)).toEqual(["power:pcie_link_state", "network:nic1a2b:eee"]);
    expect(game.map((s) => s.id)).toEqual(["game_config:mw4:shadow_quality"]);
    expect(software.length + hardware.length + game.length).toBe(rows.length);
  });
});

const grouped = (id: string, over: Partial<Setting>) => ({ ...row(id, "game"), ...over }) as Setting;

describe("gameGroups", () => {
  it("heads each game with the label the backend sent, in the backend's order", () => {
    const groups = gameGroups([
      grouped("game_config:cs2:fps_max", { groupId: "cs2", groupLabel: "Counter-Strike 2", groupOrder: 12 }),
      grouped("game_config:mw4:shadow", { groupId: "mw4", groupLabel: "Modern Warfare IV", groupOrder: 10 }),
      grouped("game_config:mw4:blur", { groupId: "mw4", groupLabel: "Modern Warfare IV", groupOrder: 10 }),
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Modern Warfare IV", "Counter-Strike 2"]);
    expect(groups[0].settings.map((s) => s.id)).toEqual(["game_config:mw4:shadow", "game_config:mw4:blur"]);
  });

  it("lists a game the backend gave no group under its own module, last", () => {
    const groups = gameGroups([
      grouped("game_config:mw4:shadow", { groupId: "mw4", groupLabel: "Modern Warfare IV", groupOrder: 10 }),
      grouped("fortnite:quality", { module: "fortnite" }),
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Modern Warfare IV", "fortnite"]);
  });
});

describe("categoryGroups", () => {
  const meta = (id: string, displayName: string, order: number) =>
    [id, { id, displayName, order }] as [string, CategoryMetadata];
  const categories = new Map([meta("system", "System Tuning", 2), meta("network", "Network", 1)]);

  it("orders categories as the backend does and names them with its words", () => {
    const groups = categoryGroups(
      [
        grouped("system:gamedvr", { category: "system" as Setting["category"] }),
        grouped("network:nagle", { category: "network" as Setting["category"] }),
      ],
      categories,
    );

    expect(groups.map((g) => g.label)).toEqual(["Network", "System Tuning"]);
  });

  it("keeps a category the backend did not describe, last, under its id", () => {
    const groups = categoryGroups(
      [
        grouped("mystery:x", { category: "mystery" as Setting["category"] }),
        grouped("network:nagle", { category: "network" as Setting["category"] }),
      ],
      categories,
    );

    expect(groups.map((g) => g.label)).toEqual(["Network", "mystery"]);
  });
});
