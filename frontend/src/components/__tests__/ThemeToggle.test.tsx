/**
 * The theme preference: light by default, a header toggle, persisted, applied
 * to the page at once.
 *
 * Each test names what a user would see go wrong: a dark page they never asked
 * for, a choice forgotten on reload, a toggle whose label does not say what it
 * will do, a header without the control.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent } from "@testing-library/react";
import { render, screen } from "../../test/utils";
import { ThemeToggle } from "../ThemeToggle";
import { TabNavigation } from "../TabNavigation";
import { setLocale } from "../../i18n";
import { tr } from "../../i18n/tr";
import { setTheme, getTheme, THEME_STORAGE_KEY } from "../../lib/theme";

function fakeStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
    data,
  };
}

let storage: ReturnType<typeof fakeStorage>;

beforeEach(() => {
  storage = fakeStorage();
  vi.stubGlobal("localStorage", storage);
  setLocale("en");
  setTheme("light");
  storage.data.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
  setTheme("light");
});

describe("the theme starts light", () => {
  it("is light, with no dark class on the page, when nothing was ever chosen", async () => {
    vi.resetModules();
    document.documentElement.classList.remove("dark");
    // The OS asking for dark must not move the default.
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: () => undefined }));

    const fresh = await import("../../lib/theme");

    expect(fresh.getTheme()).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("comes back dark, applied to the page on load, when dark was chosen earlier", async () => {
    storage.data.set(THEME_STORAGE_KEY, "dark");
    vi.resetModules();

    const fresh = await import("../../lib/theme");

    expect(fresh.getTheme()).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("treats an unrecognised stored value as the default, not as dark", async () => {
    storage.data.set(THEME_STORAGE_KEY, "solarized");
    vi.resetModules();

    const fresh = await import("../../lib/theme");

    expect(fresh.getTheme()).toBe("light");
  });
});

describe("ThemeToggle", () => {
  it("offers the switch to dark while the page is light, and says so", () => {
    render(<ThemeToggle />);

    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
  });

  it("applies dark to the page at once and remembers it", () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));

    expect(getTheme()).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
    expect(storage.data.get(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("then offers the way back, and light removes the class again", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));

    fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));

    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(storage.data.get(THEME_STORAGE_KEY)).toBe("light");
    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
  });

  it("speaks the user's language", () => {
    setLocale("tr");
    render(<ThemeToggle />);

    expect(screen.getByRole("button", { name: tr["theme.toDark"] })).toBeInTheDocument();
  });

  it("keeps working for the session when storage is blocked", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    });
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));

    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});

describe("the app header", () => {
  it("carries the theme toggle beside the language switch", () => {
    render(<TabNavigation />);

    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: tr["locale.switch"] })).toBeInTheDocument();
  });
});
