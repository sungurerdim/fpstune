/**
 * Tests for Zustand store with SettingsSlice.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "../index";
import type { SettingDefinition } from "../../types/setting";

const mockDefinitions: SettingDefinition[] = [
  {
    id: "timer:hpet",
    category: "timer",
    display_name: "HPET",
    description: "High Precision Event Timer",
    value_type: "choice",
    choices: ["enabled", "disabled"],
    default_value: "enabled",
    recommended_value: "disabled",
    requires_reboot: true,
    is_action: false,
    current_impact: "",
    recommended_impact: "",
    scope: "essential",

    applicable_conditions: {},
  },
  {
    id: "priority:gpu_priority",
    category: "core",
    display_name: "GPU Priority",
    description: "GPU scheduling priority",
    value_type: "int",
    choices: [],
    default_value: 8,
    recommended_value: 8,
    requires_reboot: false,
    is_action: false,
    current_impact: "",
    recommended_impact: "",
    scope: "essential",

    applicable_conditions: {},
  },
  {
    id: "gpu-nvidia:cuda_force_p2",
    category: "gpu",
    display_name: "CUDA Force P2 State",
    description: "Force CUDA P2 power state",
    value_type: "bool",
    choices: [],
    default_value: false,
    recommended_value: true,
    requires_reboot: false,
    is_action: false,
    current_impact: "",
    recommended_impact: "",
    scope: "essential",

    applicable_conditions: {},
  },
];

describe("useStore", () => {
  beforeEach(() => {
    // Reset store state before each test
    useStore.setState({
      settings: new Map(),
      categoryDetectionStatus: {
        core: "idle",
        timer: "idle",
        power: "idle",
        network: "idle",
        gpu: "idle",
        visual: "idle",
        storage: "idle",
        system: "idle",
        cleanup: "idle",
        maintenance: "idle",
        game: "idle",
        audio: "idle",
      },
    });
  });

  describe("initializeFromDefinitions", () => {
    it("initializes settings from definitions", () => {
      const { initializeFromDefinitions, isInitialized } = useStore.getState();

      expect(isInitialized()).toBe(false);
      initializeFromDefinitions(mockDefinitions);
      expect(isInitialized()).toBe(true);
    });

    it("creates settings with correct properties", () => {
      useStore.getState().initializeFromDefinitions(mockDefinitions);

      const updatedSettings = useStore.getState().settings;
      expect(updatedSettings.size).toBe(3);

      const timerSetting = updatedSettings.get("timer:hpet");
      expect(timerSetting).toBeDefined();
      expect(timerSetting?.displayName).toBe("HPET");
      expect(timerSetting?.category).toBe("timer");
      expect(timerSetting?.currentValue).toBeNull(); // Not yet detected
    });
  });

  describe("categoryDetectionStatus", () => {
    it("has all categories with idle status initially", () => {
      const { categoryDetectionStatus } = useStore.getState();
      expect(categoryDetectionStatus.core).toBe("idle");
      expect(categoryDetectionStatus.timer).toBe("idle");
      expect(categoryDetectionStatus.power).toBe("idle");
      expect(categoryDetectionStatus.gpu).toBe("idle");
      expect(categoryDetectionStatus.network).toBe("idle");
      expect(categoryDetectionStatus.visual).toBe("idle");
      expect(categoryDetectionStatus.storage).toBe("idle");
      expect(categoryDetectionStatus.system).toBe("idle");
      expect(categoryDetectionStatus.cleanup).toBe("idle");
      expect(categoryDetectionStatus.maintenance).toBe("idle");
    });

    it("can update category status", () => {
      useStore.getState().setSettingsCategoryStatus("core", "loading");

      const { categoryDetectionStatus } = useStore.getState();
      expect(categoryDetectionStatus.core).toBe("loading");
    });

    it("preserves other category statuses when updating one", () => {
      const store = useStore.getState();
      store.setSettingsCategoryStatus("core", "done");
      useStore.getState().setSettingsCategoryStatus("gpu", "loading");

      const { categoryDetectionStatus } = useStore.getState();
      expect(categoryDetectionStatus.core).toBe("done");
      expect(categoryDetectionStatus.gpu).toBe("loading");
      expect(categoryDetectionStatus.network).toBe("idle");
    });
  });

  /**
   * Eleven components subscribe to `_settingsVersion` and to nothing else about
   * the settings Map. A mutator that replaces the Map without bumping it is
   * therefore invisible: the store is correct and the screen is not. This is
   * how a post-apply single-setting update used to leave every row stale, so
   * the rule is checked on every writer rather than on the one that broke.
   */
  describe("_settingsVersion", () => {
    it("bumps when a single setting's detection result lands", () => {
      useStore.getState().initializeFromDefinitions(mockDefinitions);
      const before = useStore.getState()._settingsVersion;

      useStore
        .getState()
        .setSettingDetectionResult("timer:hpet", "disabled", true, true);

      expect(useStore.getState()._settingsVersion).toBeGreaterThan(before);
      expect(useStore.getState().settings.get("timer:hpet")?.currentValue).toBe(
        "disabled",
      );
    });

    it("bumps when a whole category is finalised", () => {
      useStore.getState().initializeFromDefinitions(mockDefinitions);
      const before = useStore.getState()._settingsVersion;

      useStore.getState().finalizeDetection(
        {
          "timer:hpet": {
            value: "disabled",
            is_optimized: true,
            is_applicable: true,
          },
        },
        ["timer"],
      );

      expect(useStore.getState()._settingsVersion).toBeGreaterThan(before);
      expect(useStore.getState().categoryDetectionStatus.timer).toBe("done");
    });
  });

  describe("finalizeDetection and the measured finding", () => {
    it("carries a finding with a kind onto the setting and clears it on null", () => {
      useStore.getState().initializeFromDefinitions(mockDefinitions);
      useStore.getState().finalizeDetection(
        {
          "timer:hpet": {
            value: "enabled",
            is_optimized: false,
            is_applicable: true,
            finding: { kind: "link_speed", linked_mbps: 100, ceiling_mbps: 2500 },
          },
        },
        [],
      );
      expect(useStore.getState().settings.get("timer:hpet")?.finding).toEqual({
        kind: "link_speed",
        linked_mbps: 100,
        ceiling_mbps: 2500,
      });

      // An update that says nothing about the finding leaves it standing...
      useStore.getState().finalizeDetection(
        { "timer:hpet": { value: "enabled", is_optimized: false, is_applicable: true } },
        [],
      );
      expect(useStore.getState().settings.get("timer:hpet")?.finding?.kind).toBe(
        "link_speed",
      );

      // ...and one that measured nothing this time clears it.
      useStore.getState().finalizeDetection(
        {
          "timer:hpet": {
            value: "enabled",
            is_optimized: false,
            is_applicable: true,
            finding: null,
          },
        },
        [],
      );
      expect(useStore.getState().settings.get("timer:hpet")?.finding).toBeUndefined();
    });
  });

  describe("finalizeDetection and the recorded original", () => {
    it("keeps the recorded original when an update does not carry one", () => {
      // Only the full scan records originals, and a post-apply re-detect is not
      // one. An update that omits the field must leave the recorded value
      // standing, or the undo action silently disappears after every apply.
      useStore.getState().initializeFromDefinitions(mockDefinitions);
      useStore.getState().finalizeDetection(
        {
          "timer:hpet": {
            value: "enabled",
            is_optimized: false,
            is_applicable: true,
            original_value: "enabled",
          },
        },
        [],
      );

      useStore
        .getState()
        .setSettingDetectionResult("timer:hpet", "disabled", true, true);

      expect(useStore.getState().settings.get("timer:hpet")?.originalValue).toBe(
        "enabled",
      );
    });

    it("clears the original when the backend says nothing was recorded", () => {
      useStore.getState().initializeFromDefinitions(mockDefinitions);
      useStore.getState().finalizeDetection(
        {
          "timer:hpet": {
            value: "enabled",
            is_optimized: false,
            is_applicable: true,
            original_value: "enabled",
          },
        },
        [],
      );

      useStore.getState().finalizeDetection(
        {
          "timer:hpet": {
            value: "enabled",
            is_optimized: false,
            is_applicable: true,
            original_value: null,
          },
        },
        [],
      );

      expect(
        useStore.getState().settings.get("timer:hpet")?.originalValue,
      ).toBeUndefined();
    });
  });

  describe("notifications", () => {
    beforeEach(() => {
      useStore.setState({ notifications: [] });
    });

    it("gives two notifications raised in the same millisecond distinct ids", () => {
      // `Date.now()` was the id. A bulk cleanup raises several failures inside
      // one millisecond, and removing either of a colliding pair removed both.
      const { addNotification } = useStore.getState();
      addNotification("Cleanup failed: temp files", "error");
      addNotification("Cleanup failed: browser cache", "error");

      const ids = useStore.getState().notifications.map((n) => n.id);
      expect(new Set(ids).size).toBe(2);
    });

    it("removes exactly the notification asked for", () => {
      const { addNotification } = useStore.getState();
      addNotification("first", "error");
      addNotification("second", "error");

      const [first] = useStore.getState().notifications;
      useStore.getState().removeNotification(first.id);

      const left = useStore.getState().notifications;
      expect(left).toHaveLength(1);
      expect(left[0].message).toBe("second");
    });

    it("stops growing once the cap is reached, keeping the newest", () => {
      const { addNotification } = useStore.getState();
      for (let i = 0; i < 120; i++) {
        addNotification(`failure ${i}`, "error");
      }

      const kept = useStore.getState().notifications;
      expect(kept).toHaveLength(50);
      expect(kept[kept.length - 1].message).toBe("failure 119");
    });
  });
});
