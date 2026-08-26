import { useState } from "react";
import { Rocket } from "lucide-react";
import { useT } from "../i18n";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";

const STORAGE_KEY = "fpstune-welcomed";

/**
 * The first thing a new user reads (E6).
 *
 * Before this existed, the first screen's first action was "Apply all 30" —
 * a bulk write to the registry, driver settings and game config files, with
 * nothing saying what the app is, that it had not touched anything yet, or
 * what the two-word "Not Admin" shield means. Shown once: dismissing it is
 * persisted, and a returning user is not re-welcomed.
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
    <Card className="p-4 space-y-2 border-primary/40">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <Rocket className="w-4 h-4 text-primary" aria-hidden="true" />
        {t("firstRun.title")}
      </p>
      <div className="text-sm text-muted-foreground space-y-1.5">
        <p>{t("firstRun.what")}</p>
        <p>
          <strong className="text-foreground">
            {t("firstRun.nothingChanged")}
          </strong>{" "}
          {t("firstRun.nothingChangedBody")}
        </p>
        <p>{t("firstRun.admin")}</p>
      </div>
      <Button onClick={dismiss}>{t("firstRun.dismiss")}</Button>
    </Card>
  );
}
