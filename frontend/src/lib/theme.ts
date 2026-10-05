import { useSyncExternalStore } from "react";

/**
 * The colour theme: light unless the user chose dark.
 *
 * A module-level store, like the locale, so non-component code can read it and
 * every `useTheme` consumer re-renders on a change. Two places apply the choice
 * to the page and they must agree:
 *
 *   - `index.html` runs a small inline script before the first paint, so a user
 *     who chose dark never sees a light flash while the bundle loads;
 *   - `applyTheme` below runs when this module loads and on every change, so the
 *     class and `color-scheme` follow the store afterwards.
 *
 * The operating system's preference is deliberately not consulted: the default
 * is light, and only an explicit choice (persisted under `STORAGE_KEY`) moves it.
 * `theme.test.ts` runs the inline script against both rules.
 */

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "fpstune-theme";

function initialTheme(): Theme {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    /* storage blocked: the default applies */
    return "light";
  }
}

/** Put the theme on the document: Tailwind's `dark` class, and the UA's own colour scheme. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

let currentTheme: Theme = initialTheme();
const listeners = new Set<() => void>();
applyTheme(currentTheme);

export function getTheme(): Theme {
  return currentTheme;
}

export function setTheme(theme: Theme): void {
  currentTheme = theme;
  applyTheme(theme);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* storage blocked: the in-memory choice still applies this session */
  }
  for (const listener of listeners) listener();
}

/** Re-renders the component when the theme changes. */
export function useTheme(): { theme: Theme; setTheme: (theme: Theme) => void } {
  const theme = useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => currentTheme,
    () => currentTheme,
  );
  return { theme, setTheme };
}
