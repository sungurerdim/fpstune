/**
 * One formatter prints a setting's value: `valueLabel` in `lib/finding.ts`.
 *
 * Commit 574e6c1 let the backend name a choice for the machine it runs on (the
 * NVIDIA low-latency tier "on" is "Ultra" where the driver lacks the legacy
 * keys). Only two surfaces learned it: the pill selector kept printing the raw
 * `on`, and the toggle tooltip printed `String(setting.choices[0])`, because
 * each surface formatted a value by hand. A rule that lives in one function is
 * only a rule while nothing else formats a value, so this reads the source of
 * every component and hook and fails on the hand-formatting itself.
 *
 * Its sibling `valueLabelSurfaces.test.tsx` renders the surfaces; this one
 * catches the surface nobody renders yet.
 */

import { describe, expect, it } from "vitest";

const SOURCES = import.meta.glob(
  [
    "../**/*.tsx",
    "../../hooks/**/*.{ts,tsx}",
    "!../**/__tests__/**",
    "!../../hooks/**/__tests__/**",
  ],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

const VALUE = String.raw`(?:[\w$]+(?:\??\.[\w$]+)*\.)?(?:choices\[[^\]]*\]|currentValue|recommendedValue|defaultValue|profileTarget|targetValue)`;

/** Each way a component can print a stored value without asking `valueLabel`. */
const HAND_FORMATTING: Array<[string, RegExp]> = [
  // `String(x).toLowerCase() === …` compares; it does not print.
  ["String(<value>)", new RegExp(String.raw`String\(\s*${VALUE}\s*\)(?!\s*\.)`)],
  ["String(<history entry>.value)", /String\(\s*(?:row|entry|item)\.value\s*\)/],
  ["`${<value>}`", new RegExp(String.raw`\$\{\s*${VALUE}\s*\}`)],
  ["{<value>} as JSX text", new RegExp(String.raw`>\s*\{\s*${VALUE}\s*\}\s*<|^\s*\{\s*${VALUE}\s*\}\s*$`)],
  ["<choices>.map / .join", /\.choices\s*\.(?:map|join)\(/],
  ["valueHints lookup", /\bvalueHints\??\.?\[/],
  ["choiceLabels lookup", /\bchoiceLabels\??\.?\[/],
];

function violations(source: string): string[] {
  const found: string[] = [];
  source.split("\n").forEach((line, index) => {
    const code = line.trim();
    if (code.startsWith("//") || code.startsWith("*") || code.startsWith("/*")) return;
    for (const [name, pattern] of HAND_FORMATTING) {
      if (pattern.test(line)) found.push(`line ${index + 1}: ${name}: ${code}`);
    }
  });
  return found;
}

describe("a value is printed by valueLabel and nothing else", () => {
  it("reads the components and hooks it guards", () => {
    // A glob that silently matches nothing would pass forever.
    const names = Object.keys(SOURCES);
    expect(names.some((n) => n.endsWith("/TweakSetting.tsx"))).toBe(true);
    expect(names.some((n) => n.endsWith("/ui/PillSelector.tsx"))).toBe(true);
    expect(names.some((n) => n.endsWith("/hooks/useApplySingle.ts"))).toBe(true);
  });

  it("recognises the hand-formatting it forbids", () => {
    // Each line below is a real way the bug shipped or could ship; a pattern
    // that stopped matching its own example would guard nothing.
    const bad = [
      'const x = t("row.resetChoice", { value: String(setting.choices[0]) });',
      'const x = t("row.setTo", { value: String(profileTarget) });',
      'const x = t("row.resetTo", { value: String(setting.defaultValue) });',
      'const x = t("history.value", { value: String(row.value) });',
      "const x = `Target: ${setting.recommendedValue}`;",
      "<span>{setting.currentValue}</span>",
      "{setting.currentValue}",
      "const options = setting.choices.map((c) => c);",
      "const label = valueHints?.[option] ?? option;",
      "const key = setting.choiceLabels?.[String(value)];",
    ];
    for (const line of bad) {
      expect(violations(line), line).not.toEqual([]);
    }
  });

  it("leaves the helper's own use alone", () => {
    const fine = [
      "const x = valueLabel(setting, setting.defaultValue);",
      'labelFor={(option) => valueLabel(setting, option)}',
      "const isOptimized = valuesEqual(response.new_value, setting.recommendedValue);",
      "payload[s.id] = s.recommendedValue;",
      "// String(setting.choices[0]) was the bug",
    ];
    for (const line of fine) {
      expect(violations(line), line).toEqual([]);
    }
  });

  it("finds no component or hook formatting a value by hand", () => {
    const found = Object.entries(SOURCES).flatMap(([file, source]) =>
      violations(source).map((v) => `${file} ${v}`),
    );
    expect(found, found.join("\n")).toEqual([]);
  });
});
