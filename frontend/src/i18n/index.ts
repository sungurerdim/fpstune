import { useSyncExternalStore } from "react";
import { en, type MessageKey } from "./en";
import { tr } from "./tr";

/**
 * The i18n layer (F1): two catalogues, one hook, no dependency.
 *
 * In-house rather than react-i18next, per prefer-existing-deps: two locales,
 * flat keys and `{name}` interpolation are the whole requirement, and typing
 * the Turkish catalogue against the English one gives compile-time parity —
 * a guarantee a runtime library cannot make.
 *
 * The locale is a module-level store (not React context) so non-component
 * code — hooks building notification strings, api helpers — can translate
 * too. An explicit choice persists; otherwise the browser's language decides.
 */

export type Locale = "en" | "tr";

const STORAGE_KEY = "fpstune-locale";
const CATALOGUES: Record<Locale, Record<MessageKey, string>> = { en, tr };

function initialLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "tr") return stored;
  } catch {
    /* storage blocked: fall through to the browser's language */
  }
  return typeof navigator !== "undefined" &&
    navigator.language?.toLowerCase().startsWith("tr")
    ? "tr"
    : "en";
}

let currentLocale: Locale = initialLocale();
const listeners = new Set<() => void>();

export function getLocale(): Locale {
  return currentLocale;
}

export function setLocale(locale: Locale): void {
  currentLocale = locale;
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* storage blocked: the in-memory choice still applies this session */
  }
  for (const listener of listeners) listener();
}

/** Translate a key, with `{name}` interpolation. */
export function t(
  key: MessageKey,
  params?: Record<string, string | number>,
): string {
  let message = CATALOGUES[currentLocale][key];
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      message = message.split(`{${name}}`).join(String(value));
    }
  }
  return message;
}

/** Re-renders the component when the locale changes. Returns [t, locale]. */
export function useT(): { t: typeof t; locale: Locale } {
  const locale = useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => currentLocale,
    () => currentLocale,
  );
  return { t, locale };
}
