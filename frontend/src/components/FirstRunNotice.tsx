import { useState } from "react";
import { Rocket } from "lucide-react";
import { useT } from "../i18n";
import { Button } from "./ui/Button";

const STORAGE_KEY = "fpstune-welcomed";

/**
 * The first thing a new user reads (E6), as one banner above the panel.
 *
 * Before this existed, the first screen's first action was "Apply all 30" —
 * a bulk write to the registry, driver settings and game config files, with
 * nothing saying that the app had not touched anything yet, or what the
 * two-word "Not Admin" shield means. Shown once: dismissing it is persisted,
 * and a returning user is not re-welcomed. A banner rather than a card: it is
 * about the app, not about the tab under it, and the tweaks are what the
 * screen is for.
 */
export function FirstRunNotice() {
  const { t } = useT();
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "true";
    } catch {
      // Storage blocked: show it every time rather than never.
      return false;
    }
  });

  if (dismissed) return null;

  const dismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(STORAGE_KEY, "true");
    } catch {
      /* storage blocked: the session state above still hides it */
    }
  };

  return (
    <div
      role="status"
      className="mb-2 flex items-start gap-2 rounded-md border border-primary/40 bg-primary/5 px-3 py-2"
    >
      <Rocket className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
      <p className="min-w-0 flex-1 text-xs text-muted-foreground">
        <strong className="text-sm text-foreground">{t("firstRun.title")}</strong>{" "}
        <strong className="text-foreground">{t("firstRun.nothingChanged")}</strong>{" "}
        {t("firstRun.nothingChangedBody")} {t("firstRun.admin")}
      </p>
      <Button size="xs" className="shrink-0" onClick={dismiss}>
        {t("firstRun.dismiss")}
      </Button>
    </div>
  );
}
