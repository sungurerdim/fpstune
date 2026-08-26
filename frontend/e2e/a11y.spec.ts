/**
 * E7: the contrast check jsdom cannot run.
 *
 * Axe against the rendered landing page in a real browser, WCAG 2.1 AA. The
 * backend is not running, so this audits the static shell — colours, focus,
 * landmarks — which is exactly the layer the token system owns.
 */

import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("the landing page passes WCAG 2.1 AA, including colour contrast", async ({
  page,
}) => {
  await page.goto("/");
  // The shell renders synchronously; give the first paint a beat.
  await page.waitForSelector("#root > *");

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();

  const readable = results.violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help} — ${v.nodes
        .slice(0, 3)
        .map((n) => n.target.join(" "))
        .join(", ")}`,
  );
  expect(readable, readable.join("\n")).toEqual([]);
});
