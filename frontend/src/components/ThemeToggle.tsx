import { Moon, Sun } from "lucide-react";
import { useT } from "../i18n";
import { useTheme } from "../lib/theme";

/**
 * The light/dark switch, in the app header beside the language switch.
 *
 * One button whose accessible name says what a press will do ("Switch to dark
 * theme"), and whose icon shows the theme it would switch to, so the control
 * reads the same to a screen reader and to the eye. The choice persists and is
 * applied before first paint (`lib/theme.ts`, `index.html`).
 */
export function ThemeToggle() {
  const { t } = useT();
  const { theme, setTheme } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  const label = t(next === "dark" ? "theme.toDark" : "theme.toLight");
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={label}
      title={label}
      data-theme-toggle={theme}
      className="rounded border border-border p-1 text-muted-foreground transition-colors hover:bg-muted"
    >
      {next === "dark" ? (
        <Moon className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <Sun className="h-3.5 w-3.5" aria-hidden />
      )}
    </button>
  );
}
