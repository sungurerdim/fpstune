/**
 * A monitor below its own best mode says what is wrong and what fixing it buys,
 * in the panel's own numbers — and a secondary one says it is optional.
 */

import { describe, it, expect, afterEach } from "vitest";
import { describeFinding } from "../finding";
import { setLocale } from "../../i18n";
import type { Setting } from "../../types/setting";

function monitor(finding: Record<string, unknown>): Setting {
  return { finding: { kind: "display_mode", ...finding } } as unknown as Setting;
}

const base = {
  width: 2560,
  height: 1440,
  refresh_hz: 60,
  native_width: 2560,
  native_height: 1440,
  max_refresh_hz: 165,
  primary: true,
};

afterEach(() => setLocale("en"));

describe("display_mode finding", () => {
  it("names the refresh it runs at, the one it can do, and the frame time each costs", () => {
    const text = describeFinding(monitor(base))!;
    expect(text.summary).toContain("Running at 60 Hz; this panel can show 165 Hz");
    expect(text.summary).toContain("6.1 ms instead of 16.7 ms");
    expect(text.advice).toContain("15 seconds");
  });

  it("says a secondary monitor is optional and why", () => {
    const text = describeFinding(monitor({ ...base, primary: false }))!;
    expect(text.summary).toContain("Secondary monitor, so optional");
  });

  it("names a resolution below native", () => {
    const text = describeFinding(monitor({ ...base, width: 1920, height: 1080, refresh_hz: 165 }))!;
    expect(text.summary).toContain("Running at 1920×1080; the panel's native resolution is 2560×1440");
  });

  it("states the native mode when there is nothing to fix", () => {
    const text = describeFinding(monitor({ ...base, refresh_hz: 165 }))!;
    expect(text).toEqual({ summary: "Running at its native 2560×1440 @ 165 Hz.", advice: "" });
  });

  it("speaks Turkish with the same numbers", () => {
    setLocale("tr");
    const text = describeFinding(monitor(base))!;
    expect(text.summary).toContain("60 Hz'de çalışıyor; bu panel 165 Hz gösterebiliyor");
  });
});
