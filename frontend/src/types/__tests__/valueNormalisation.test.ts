import { describe, expect, it } from "vitest";
import { formatSettingValue, valuesEqual } from "../setting";

/**
 * Guards a bug that reached a user: `0.5` and `0.500000` are the same number,
 * and the UI rendered them as "0.5 → 0.500000" — a row showing a difference
 * that did not exist. Because the comparison agreed with the display, the
 * setting also never cleared its Apply badge: it had been applied correctly and
 * kept reporting as drifted.
 *
 * The cause is that the two sides of a row genuinely arrive in different
 * shapes. Game configs store `0.500000`; a slider sends `0.5`; the API carries
 * a recommendation as a string beside a detected value that arrived as a
 * number. Strict equality is wrong for all three.
 */
describe("valuesEqual matches the backend's coercion", () => {
  it("treats the same number written differently as equal", () => {
    expect(valuesEqual("0.5", "0.500000")).toBe(true);
    expect(valuesEqual("0", "0.000000")).toBe(true);
    expect(valuesEqual("1", "1.000000")).toBe(true);
    expect(valuesEqual("100", "100.0")).toBe(true);
  });

  it("compares numbers across types", () => {
    expect(valuesEqual(0.5, "0.500000")).toBe(true);
    expect(valuesEqual("0.500000", 0.5)).toBe(true);
    expect(valuesEqual(30, "30")).toBe(true);
  });

  it("still separates different numbers", () => {
    expect(valuesEqual("0.5", "0.750000")).toBe(false);
    expect(valuesEqual(297, 300)).toBe(false);
  });

  it("compares booleans across types", () => {
    expect(valuesEqual(true, "true")).toBe(true);
    expect(valuesEqual("false", false)).toBe(true);
    expect(valuesEqual("true", "false")).toBe(false);
  });

  it("never reads a boolean as the number one", () => {
    // `Number(true)` is 1, so a numeric branch placed first would call these equal.
    expect(valuesEqual(true, 1)).toBe(false);
    expect(valuesEqual(false, 0)).toBe(false);
    expect(valuesEqual("true", "1")).toBe(false);
  });

  it("never reads an empty value as zero", () => {
    // `Number("")` is 0. An unset audio device is not a volume of zero.
    expect(valuesEqual("", "0.000000")).toBe(false);
    expect(valuesEqual("", 0)).toBe(false);
  });

  it("leaves values that merely contain digits as text", () => {
    expect(valuesEqual("2560x1440", "2560x1440")).toBe(true);
    expect(valuesEqual("2560x1440", "1920x1080")).toBe(false);
    expect(valuesEqual("Auto:300.000", "Auto:300.000")).toBe(true);
    expect(valuesEqual("aniso 16x", "aniso 8x")).toBe(false);
  });

  it("keeps comparing text case-insensitively", () => {
    expect(valuesEqual("QUALITY_LOW", "quality_low")).toBe(true);
    expect(valuesEqual("Off", "off")).toBe(true);
  });

  it("treats a missing value as unequal rather than as zero or empty", () => {
    expect(valuesEqual(null, "0.000000")).toBe(false);
    expect(valuesEqual(undefined, "")).toBe(false);
  });
});

describe("formatSettingValue normalises what it shows", () => {
  it("renders the same number the same way whatever shape it arrived in", () => {
    expect(formatSettingValue("0.500000")).toBe("0.5");
    expect(formatSettingValue(0.5)).toBe("0.5");
    expect(formatSettingValue("1.000000")).toBe("1");
    expect(formatSettingValue("0.000000")).toBe("0");
    expect(formatSettingValue(1)).toBe("1");
  });

  it("keeps precision the old formatting threw away", () => {
    // The previous implementation used toFixed(1), so 0.75 displayed as "0.8"
    // and two distinct values rendered identically.
    expect(formatSettingValue("0.750000")).toBe("0.75");
    expect(formatSettingValue(0.25)).toBe("0.25");
    expect(formatSettingValue("0.031623")).toBe("0.0316");
  });

  it("leaves non-numeric values alone", () => {
    expect(formatSettingValue("2560x1440")).toBe("2560x1440");
    expect(formatSettingValue("Auto:300.000")).toBe("Auto:300.000");
    expect(formatSettingValue("QUALITY_LOW")).toBe("QUALITY_LOW");
    expect(formatSettingValue("aniso 16x")).toBe("aniso 16x");
  });

  it("keeps booleans readable", () => {
    expect(formatSettingValue(true)).toBe("Enabled");
    expect(formatSettingValue(false)).toBe("Disabled");
  });

  it("shows a missing value as a dash, not as zero", () => {
    expect(formatSettingValue(null)).toBe("-");
    expect(formatSettingValue(undefined)).toBe("-");
  });

  it("renders both sides of the row that reported the bug identically", () => {
    // "Currently 0.5 → recommended 0.500000" is what the user saw.
    expect(formatSettingValue(0.5)).toBe(formatSettingValue("0.500000"));
    expect(formatSettingValue(0)).toBe(formatSettingValue("0.000000"));
  });
});
