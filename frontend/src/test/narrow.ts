/**
 * The narrow-width text rules, as one machine check any rendered surface can be put through.
 *
 * jsdom measures nothing, so "this text spills at 390px" cannot be asserted as
 * pixels. What can be asserted is the *classes* that make a browser behave, and
 * commit e957523 ("no text spills, overlaps or slides off-screen at any width")
 * fixed three kinds of defect that were all one class-shaped cause:
 *
 *  - R1 `clipped-without-title` (fix 6, `HistoryTab`, `AudioSection`): a name
 *    clipped by `truncate` is unreadable in full unless a `title` carries it.
 *  - R2 `unbroken-without-wrap` (fix 7, `ActionRow`): a long unbroken token (a
 *    path, a command) spilled out of its row because nothing told it to wrap or
 *    clip (`wrap-break-word`).
 *  - R3 `flex-item-without-min-w-0` (fixes 6 and 7, `AudioSection`, `ActionRow`):
 *    a flex item's automatic minimum width is its content, so a truncating or
 *    wrapping child inside it never gets narrower than the unbroken text
 *    unless *every* flex item on the way up says `min-w-0`.
 *  - R4 `nowrap-without-clip` (fix 1, `TabNavigation`): `whitespace-nowrap` text
 *    that can neither be clipped nor scrolled is a guaranteed spill.
 *
 * Rules read the class tokens a mobile-first stylesheet applies at the narrowest
 * width: tokens with a variant prefix (`md:`, `lg:`, `hover:`) do not apply at
 * 390px and are ignored. The rules are the same ones whatever the surface, which
 * is the point: a new row is held to them by adding it to
 * `NarrowWidth.test.tsx`, not by writing another one-off assertion.
 */

import type { Setting } from "../types/setting";
import { settingsTr } from "../i18n/settingsTr";

/** A run of non-space characters this long cannot wrap at a space. */
export const UNBROKEN_MIN = 24;

/** Classes that let a word break inside itself (and therefore shrink min-content). */
const BREAKS_ANYWHERE = new Set(["wrap-anywhere", "break-all"]);
/** Classes that wrap an overlong token inside the box (min-content unchanged). */
const WRAPS = new Set(["wrap-break-word", "break-words", ...BREAKS_ANYWHERE]);
const CLIPS = (token: string) =>
  token === "truncate" ||
  token === "overflow-hidden" ||
  token === "overflow-clip" ||
  token === "overflow-auto" ||
  token === "overflow-x-auto" ||
  token === "overflow-scroll" ||
  token === "overflow-x-scroll" ||
  /^line-clamp-\d+$/.test(token);

/**
 * The class tokens in force at the narrowest width, plus the same policies when
 * written as an inline style (`style={{ wordBreak: "break-word" }}` is the
 * browser's own `wrap-anywhere`): a rule that read only classes would call a
 * working row broken.
 */
function tokens(el: Element): Set<string> {
  const raw = el.getAttribute("class") ?? "";
  const found = new Set(raw.split(/\s+/).filter((t) => t && !t.includes(":")));
  const style = (el as HTMLElement).style;
  if (style) {
    if (style.wordBreak === "break-word" || style.wordBreak === "break-all") {
      found.add("wrap-anywhere");
    }
    if (style.overflowWrap === "anywhere") found.add("wrap-anywhere");
    if (style.overflowWrap === "break-word") found.add("wrap-break-word");
  }
  return found;
}

function lineage(el: Element, root: Element): Element[] {
  const chain: Element[] = [];
  for (let at: Element | null = el; at; at = at.parentElement) {
    chain.push(at);
    if (at === root) break;
  }
  return chain;
}

function anyUp(el: Element, root: Element, test: (t: string) => boolean): boolean {
  return lineage(el, root).some((e) => [...tokens(e)].some(test));
}

function isFlexRowItem(el: Element): boolean {
  const parent = el.parentElement;
  if (!parent) return false;
  const t = tokens(parent);
  return (
    (t.has("flex") || t.has("inline-flex")) &&
    !t.has("flex-col") &&
    !t.has("flex-col-reverse")
  );
}

function shrinkable(el: Element): boolean {
  return [...tokens(el)].some((t) => t === "min-w-0" || /^min-w-/.test(t) || CLIPS(t));
}

function longestRun(text: string): number {
  return text.split(/\s+/).reduce((max, word) => Math.max(max, word.length), 0);
}

function directText(el: Element): string {
  return Array.from(el.childNodes)
    .filter((n) => n.nodeType === 3)
    .map((n) => n.textContent ?? "")
    .join("");
}

function outline(el: Element): string {
  const tag = el.tagName.toLowerCase();
  const cls = [...tokens(el)].slice(0, 6).join(" ");
  return `<${tag}${cls ? ` class="${cls}"` : ""}>`;
}

export interface NarrowReport {
  /** Rule violations, one line each: rule · element · text excerpt. */
  violations: string[];
  /** How many elements carried each probe: a probe nobody rendered proves nothing. */
  carriers: Record<string, number>;
}

/**
 * Check every element under `root` whose own text contains one of `probes`.
 *
 * `root` is where the surface ends (a tooltip's portal content, a rendered
 * container); the walk up never leaves it.
 */
export function narrowReport(root: Element, probes: Record<string, string>): NarrowReport {
  const violations: string[] = [];
  const carriers: Record<string, number> = Object.fromEntries(
    Object.keys(probes).map((k) => [k, 0]),
  );
  const seen = new Set<string>();
  const everything = [root, ...Array.from(root.querySelectorAll("*"))];
  for (const el of everything) {
    const own = directText(el);
    if (!own.trim()) continue;
    const labels = Object.entries(probes)
      .filter(([, text]) => own.includes(text))
      .map(([label]) => label);
    if (labels.length === 0) continue;
    for (const label of labels) carriers[label] += 1;

    const text = own.trim();
    const excerpt = `${labels.join("+")}: "${text.slice(0, 40)}"`;
    const flag = (rule: string, at: Element) => {
      const line = `${rule} ${outline(at)} ${excerpt}`;
      if (!seen.has(line)) {
        seen.add(line);
        violations.push(line);
      }
    };

    const chain = lineage(el, root);
    const unbroken = longestRun(text) >= UNBROKEN_MIN;
    const clipped = anyUp(el, root, (t) => t === "truncate" || /^line-clamp-\d+$/.test(t));

    // R1: a clipped carrier names itself in full on hover (its own or an ancestor's title).
    if (clipped) {
      const titled = chain.some((e) => (e.getAttribute("title") ?? "").includes(text));
      if (!titled) flag("R1 clipped-without-title", el);
    }

    // R4: nowrap text must be clipped or scrollable by something above it.
    if (anyUp(el, root, (t) => t === "whitespace-nowrap" || t === "text-nowrap")) {
      if (!anyUp(el, root, CLIPS)) flag("R4 nowrap-without-clip", el);
    }

    if (unbroken) {
      // R2: a token that cannot wrap at a space needs a wrap or clip policy.
      if (!anyUp(el, root, (t) => WRAPS.has(t) || CLIPS(t))) {
        flag("R2 unbroken-without-wrap", el);
      }
      // R3: every flex item above the token must be allowed to shrink below it.
      if (!anyUp(el, root, (t) => BREAKS_ANYWHERE.has(t))) {
        for (const item of chain) {
          if (item === root) break;
          if (isFlexRowItem(item) && !shrinkable(item)) {
            flag("R3 flex-item-without-min-w-0", item);
          }
        }
      }
    }
  }
  return { violations, carriers };
}

// ---------------------------------------------------------------------------
// Fixtures: the longest real Turkish copy, and a token no space can break.
// ---------------------------------------------------------------------------

function longest(values: Array<[string, string]>): [string, string] {
  return values.reduce((best, cur) => (cur[1].length > best[1].length ? cur : best));
}

const entries = Object.entries(settingsTr);

/** The setting whose real Turkish name and description together are the longest. */
const [LONGEST_ID] = longest(
  entries.map(([id, e]): [string, string] => [id, e.name + e.description]),
);
const LONGEST_ENTRY = settingsTr[LONGEST_ID];
/** The longest real Turkish "what you can do" sentence in the catalogue. */
const [, LONGEST_EFFECT] = longest(
  entries.map(([id, e]): [string, string] => [id, e.effect ?? ""]),
);

export const CATALOGUE = {
  id: LONGEST_ID,
  name: LONGEST_ENTRY.name,
  description: LONGEST_ENTRY.description,
  /** What the row renders: the entry's own effect when it has one. */
  effect: LONGEST_ENTRY.effect || LONGEST_EFFECT,
} as const;

/**
 * An unbroken token made of real Turkish catalogue words, joined by underscores
 * (not a break opportunity): the shape of a path or a command, in the language
 * whose letters are widest and most likely to be mis-measured.
 */
export const UNBROKEN = [CATALOGUE.name, CATALOGUE.description, CATALOGUE.effect]
  .join(" ")
  .split(/\s+/)
  .filter((w) => w.length > 5)
  .slice(0, 8)
  .join("_");

/**
 * A setting every user-visible text field of which is long.
 *
 * `unbroken`: each field is the same token no space can break (id is left
 * unlisted in the Turkish table so the English fields are what render).
 * `catalogue`: the id of the longest real Turkish copy, so the active-locale
 * lookup returns the catalogue's own name and description; the English fields
 * hold the longest real Turkish sentences too, for the paths that do not look up.
 */
export function narrowSetting(
  kind: "unbroken" | "catalogue",
  overrides: Partial<Setting> = {},
): Setting {
  const long = kind === "unbroken" ? UNBROKEN : CATALOGUE.description;
  const id = (
    kind === "unbroken" ? `narrowprobe:${UNBROKEN}` : CATALOGUE.id
  ) as Setting["id"];
  return {
    id,
    domain: "software",
    module: id.split(":")[0],
    name: id.split(":").slice(1).join(":"),
    displayName: kind === "unbroken" ? UNBROKEN : CATALOGUE.name,
    shortName: kind === "unbroken" ? UNBROKEN : CATALOGUE.name,
    description: long,
    category: "network",
    valueType: "choice",
    choices: ["enabled", "disabled"],
    defaultValue: "enabled",
    recommendedValue: "disabled",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: `${long.slice(0, 12)}: ${long}`,
    recommendedImpact: `${long.slice(0, 12)}: ${long}`,
    effect: kind === "unbroken" ? UNBROKEN : CATALOGUE.effect,
    lastError: long,
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "enabled",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
    ...overrides,
  };
}
