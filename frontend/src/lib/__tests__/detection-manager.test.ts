/**
 * The manager's job is to put a detect response into the store without losing
 * any of it. It had two ways of doing that and they disagreed.
 *
 * `detectCategory` finalised through `finalizeDetection`, which carries all six
 * fields and bumps `_settingsVersion`. The post-apply re-detect went through a
 * second path that mapped four fields and bumped nothing — so applying a
 * setting blanked its `recommendedValue` and `originalValue` (taking the undo
 * action with them) and left eleven subscribed components rendering the values
 * from before the apply. Both of those are checked here, because both were
 * invisible: the store held the right value and the screen showed the old one.
 *
 * The suite this replaced asserted that each method was `typeof "function"` and
 * returned a Promise. It passed throughout the whole period the bug existed.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { detectionManager } from "../detection-manager";
import { settingsApi } from "../api";
import { useStore } from "../../store";
import type { SettingDefinition } from "../../types/setting";
import type { DetectResponse } from "../api";

vi.mock("../api", () => ({
  settingsApi: {
    detect: vi.fn(),
    getDefinitions: vi.fn(),
    getCategoriesMetadata: vi.fn(),
  },
}));

const mockedDetect = vi.mocked(settingsApi.detect);

const HPET: SettingDefinition = {
  id: "timer:hpet",
  category: "timer",
  display_name: "HPET",
  description: "High Precision Event Timer.",
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
};

/** One result in the backend's own field spelling, all six fields present. */
function detectResponse(
  overrides: Partial<{
    value: unknown;
    is_optimized: boolean;
    recommended_value: unknown;
    original_value: unknown;
  }> = {},
): DetectResponse {
  return {
    results: {
      "timer:hpet": {
        setting_id: "timer:hpet",
        value: "disabled",
        error: null,
        time_ms: 4,
        success: true,
        is_optimized: true,
        is_applicable: true,
        applicable_reason: "",
        recommended_value: "disabled",
        original_value: "enabled",
        ...overrides,
      },
    },
    total_time_ms: 4,
    success_count: 1,
    error_count: 0,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({
    settings: new Map(),
    categoryDetectionStatus: { timer: "idle" },
    _settingsVersion: 0,
  });
  useStore.getState().initializeFromDefinitions([HPET]);
});

describe("redetectSettings", () => {
  it("carries the recommended value and the recorded original through", async () => {
    mockedDetect.mockResolvedValue(detectResponse());

    await detectionManager.redetectSettings(["timer:hpet"]);

    const setting = useStore.getState().settings.get("timer:hpet");
    expect(setting?.currentValue).toBe("disabled");
    expect(setting?.recommendedValue).toBe("disabled");
    // Present and different from the current value is what makes the undo
    // action offerable; the lossy path dropped it and the action vanished.
    expect(setting?.originalValue).toBe("enabled");
  });

  it("bumps the version the subscribed components render on", async () => {
    mockedDetect.mockResolvedValue(detectResponse());
    const before = useStore.getState()._settingsVersion;

    await detectionManager.redetectSettings(["timer:hpet"]);

    expect(useStore.getState()._settingsVersion).toBeGreaterThan(before);
  });

  it("claims no category is done, because it re-detected a hand-picked set", async () => {
    mockedDetect.mockResolvedValue(detectResponse());

    await detectionManager.redetectSettings(["timer:hpet"]);

    expect(useStore.getState().categoryDetectionStatus.timer).toBe("idle");
  });

  it("asks for nothing when given no ids", async () => {
    await detectionManager.redetectSettings([]);

    expect(mockedDetect).not.toHaveBeenCalled();
  });

  it("shares one request between concurrent calls for the same ids", async () => {
    mockedDetect.mockResolvedValue(detectResponse());

    await Promise.all([
      detectionManager.redetectSettings(["timer:hpet"]),
      detectionManager.redetectSettings(["timer:hpet"]),
    ]);

    expect(mockedDetect).toHaveBeenCalledTimes(1);
  });

  it("leaves the store untouched when detection fails", async () => {
    mockedDetect.mockRejectedValue(new Error("backend unreachable"));
    const before = useStore.getState().settings.get("timer:hpet")?.currentValue;

    await expect(
      detectionManager.redetectSettings(["timer:hpet"]),
    ).resolves.toBeUndefined();

    expect(useStore.getState().settings.get("timer:hpet")?.currentValue).toBe(
      before,
    );
  });
});

describe("detectCategory", () => {
  it("marks the category done and carries every field", async () => {
    mockedDetect.mockResolvedValue(detectResponse());

    await detectionManager.detectCategory("timer");

    expect(useStore.getState().categoryDetectionStatus.timer).toBe("done");
    const setting = useStore.getState().settings.get("timer:hpet");
    expect(setting?.recommendedValue).toBe("disabled");
    expect(setting?.originalValue).toBe("enabled");
  });

  it("marks the category errored rather than done when detection fails", async () => {
    mockedDetect.mockRejectedValue(new Error("backend unreachable"));

    await detectionManager.detectCategory("timer");

    expect(useStore.getState().categoryDetectionStatus.timer).toBe("error");
  });

  it("detects nothing for maintenance, which has no detectable settings", async () => {
    useStore.setState({ categoryDetectionStatus: { maintenance: "idle" } });

    await detectionManager.detectCategory("maintenance");

    expect(mockedDetect).not.toHaveBeenCalled();
    expect(useStore.getState().categoryDetectionStatus.maintenance).toBe("done");
  });
});
