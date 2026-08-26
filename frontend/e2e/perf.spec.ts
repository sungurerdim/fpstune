/**
 * G3's paint half: cold-start first paint, measured where paint exists.
 *
 * jsdom paints nothing, so the budget lives here with the axe run: real
 * Chromium, production build, no backend — the shell's own cost, which is
 * what a user waits on before any data arrives. The budget is deliberately
 * loose (2s on a dev machine for a local static page is already damning);
 * it exists to catch a bundle regression, not to benchmark the machine.
 */

import { test, expect } from "@playwright/test";

test("first contentful paint of the shell stays under budget", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForSelector("#root > *");

  const fcp = await page.evaluate(() => {
    const [entry] = performance.getEntriesByName("first-contentful-paint");
    return entry ? entry.startTime : null;
  });

  expect(fcp, "no first-contentful-paint entry was recorded").not.toBeNull();
  expect(fcp!).toBeLessThan(2000);
});
