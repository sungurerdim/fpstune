import { vi } from "vitest";

/**
 * A page's layout at a given window width, as text a snapshot can pin.
 *
 * The app decides layout in CSS: Tailwind's mobile-first `min-width` variants
 * (`xl:grid-cols-2`) on a base class (`grid-cols-1`). jsdom evaluates no media
 * query and measures no box, so a DOM snapshot taken at "390px" and at "2560px"
 * would be the same string. What can be pinned is what the stylesheet *would*
 * resolve: this reads each element's class list, applies the breakpoints that
 * match the width exactly as Tailwind orders them (the widest matching variant
 * of a utility wins), and writes the layout-bearing utilities of the elements
 * that carry any.
 *
 * `BREAKPOINTS_PX` is Tailwind v4's defaults plus the app's own
 * `--breakpoint-3xl` from `index.css`; `layoutOutline.test.ts` fails if that
 * declaration and this table drift apart.
 */

/** min-width of each breakpoint variant, in CSS px, in the order they override. */
export const BREAKPOINTS_PX: ReadonlyArray<readonly [string, number]> = [
  ["sm", 640],
  ["md", 768],
  ["lg", 1024],
  ["xl", 1280],
  ["2xl", 1536],
  ["3xl", 1920],
];

/** A utility family: later matching breakpoints replace the earlier value. */
const FAMILIES: ReadonlyArray<readonly [string, RegExp]> = [
  ["display", /^(hidden|block|inline-block|inline|flex|inline-flex|grid|contents)$/],
  ["grid-cols", /^grid-cols-.+$/],
  ["col-span", /^col-span-.+$/],
  ["flex-dir", /^flex-(row|col|row-reverse|col-reverse)$/],
  ["flex-wrap", /^flex-(wrap|nowrap|wrap-reverse)$/],
  ["max-w", /^max-w-.+$/],
  ["order", /^-?order-.+$/],
];

function breakpointOrder(variant: string): number {
  return BREAKPOINTS_PX.findIndex(([name]) => name === variant);
}

/**
 * The layout utilities in force on one element at `width`, by family.
 *
 * Variants that are not a width breakpoint (`hover:`, `focus-visible:`,
 * `aria-selected:`, `dark:`) describe a state, not a window, and never apply.
 */
export function resolveLayout(className: string, width: number): Record<string, string> {
  const resolved = new Map<string, { rank: number; value: string }>();
  for (const token of className.split(/\s+/).filter(Boolean)) {
    const parts = token.split(":");
    const utility = parts[parts.length - 1];
    const variants = parts.slice(0, -1);

    let rank = -1; // base utility
    let applies = true;
    for (const variant of variants) {
      const at = breakpointOrder(variant);
      if (at === -1 || width < BREAKPOINTS_PX[at][1]) {
        applies = false;
        break;
      }
      rank = Math.max(rank, at);
    }
    if (!applies) continue;

    const family = FAMILIES.find(([, pattern]) => pattern.test(utility));
    if (!family) continue;
    const held = resolved.get(family[0]);
    if (!held || rank >= held.rank) resolved.set(family[0], { rank, value: utility });
  }
  return Object.fromEntries([...resolved].map(([family, { value }]) => [family, value]));
}

function describeElement(el: Element): string {
  const tag = el.tagName.toLowerCase();
  const testId = el.getAttribute("data-testid");
  if (testId) return `${tag}#${testId}`;
  const role = el.getAttribute("role");
  if (role) return `${tag}[${role}]`;
  if (/^h[1-6]$/.test(tag)) return `${tag} "${(el.textContent ?? "").trim().slice(0, 48)}"`;
  return tag;
}

/**
 * One line per element that carries a test id, a heading, or a layout utility
 * that matters at this width, indented by how many such elements enclose it.
 *
 * `display` is reported only where it removes the element (`hidden`), because
 * `flex` and `block` are on nearly everything and would bury the columns.
 */
export function layoutOutline(root: Element, width: number): string {
  const lines: string[] = [`viewport ${width}px`];

  const walk = (el: Element, depth: number) => {
    const layout = resolveLayout(el.getAttribute("class") ?? "", width);
    if (layout.display && layout.display !== "hidden") delete layout.display;
    const marks = Object.values(layout);
    const landmark = el.hasAttribute("data-testid") || /^h[1-6]$/.test(el.tagName.toLowerCase());

    let childDepth = depth;
    if (marks.length > 0 || landmark) {
      lines.push(`${"  ".repeat(depth)}${describeElement(el)}${marks.length ? ` [${marks.join(" ")}]` : ""}`);
      childDepth = depth + 1;
    }
    for (const child of Array.from(el.children)) walk(child, childDepth);
  };

  for (const child of Array.from(root.children)) walk(child, 0);
  return lines.join("\n");
}

/**
 * Put the window at `width`: `innerWidth`, and a `matchMedia` that answers
 * `min-width` / `max-width` queries against it the way a browser would.
 */
export function setViewport(width: number): void {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: width });

  const evaluate = (query: string): boolean => {
    const clauses = Array.from(query.matchAll(/\(\s*(min|max)-width\s*:\s*([\d.]+)(px|rem|em)\s*\)/g));
    if (clauses.length === 0) return false;
    return clauses.every(([, bound, amount, unit]) => {
      const px = Number(amount) * (unit === "px" ? 1 : 16);
      return bound === "min" ? width >= px : width <= px;
    });
  };

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: evaluate(query),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    })),
  });
}
