import { defineConfig } from "@playwright/test";

/**
 * Browser-level checks only (E7): axe's colour-contrast rule needs computed
 * styles, which jsdom does not produce — so this project exists solely for
 * what vitest cannot see. `vite preview` serves the production build; the
 * backend is absent on purpose, the static DOM is what gets audited.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
  },
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
