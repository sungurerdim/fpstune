/**
 * The definitions endpoint is where a setting's enums enter the app.
 *
 * Before this boundary was narrowed, `definitionToSetting` cast the wire strings
 * straight into their unions. A backend that renamed a scope, a risk level or a
 * domain — or a stale frontend against a newer backend — put a value no branch
 * knows into the store: the row could never match a bulk level, the risk chip
 * fell through its comparison, and the only symptom was a setting that silently
 * stopped being offered.
 *
 * These pin the two halves of the contract: what the backend sent is kept, and
 * what it did not send (or sent outside the set) becomes a value that renders.
 */

import { describe, expect, it } from "vitest";
import { definitionToSetting, type SettingDefinition } from "../setting";

const BASE: SettingDefinition = {
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
  domain: "software",
};

describe("definitionToSetting keeps a definition inside the contract", () => {
  it("carries the backend's own enums through unchanged", () => {
    const setting = definitionToSetting({
      ...BASE,
      risk_level: "advanced",
      evidence_level: "experimental",
      domain: "game",
      scope: "complete",
      value_type: "bool",
    });

    expect(setting.valueType).toBe("bool");
    expect(setting.scope).toBe("complete");
    expect(setting.domain).toBe("game");
    expect(setting.riskLevel).toBe("advanced");
    expect(setting.evidenceLevel).toBe("experimental");
  });

  it("uses the documented fallbacks when a field is absent", () => {
    const setting = definitionToSetting(BASE);

    expect(setting.riskLevel).toBe("low");
    expect(setting.evidenceLevel).toBe("likely");
  });
});

describe("definitionToSetting refuses a value outside the contract", () => {
  it("normalises every enum rather than carrying the stranger into the UI", () => {
    // A backend/frontend version skew, spelled as the wire would spell it.
    const setting = definitionToSetting({
      ...BASE,
      value_type: "tri-state",
      scope: "ultra",
      domain: "cloud",
      risk_level: "extreme",
      evidence_level: "anecdotal",
    } as unknown as SettingDefinition);

    expect(setting.valueType).toBe("string");
    expect(setting.scope).toBe("recommended");
    expect(setting.domain).toBe("software");
    expect(setting.riskLevel).toBe("low");
    expect(setting.evidenceLevel).toBe("likely");
  });
});
