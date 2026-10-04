import { useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { useT } from "../i18n";
import { updateApi, type UpdateStatus } from "../lib/api";
import { useStore } from "../store";

/**
 * Release check and self-update, both on the user's own press. Nothing here
 * reaches the network on load: the check is a click, and the install is a
 * second click on what that check found.
 */
export function UpdateControl() {
  const { t } = useT();
  const addNotification = useStore((s) => s.addNotification);
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [busy, setBusy] = useState<"checking" | "installing" | null>(null);

  async function check() {
    setBusy("checking");
    try {
      const result = await updateApi.check();
      setStatus(result);
      if (result.error) {
        addNotification(t("update.unreachable", { reason: result.error }), "warning");
      } else if (result.update_available && result.latest) {
        addNotification(
          t("update.available", { latest: result.latest, current: result.current }),
          "info",
        );
      } else {
        addNotification(t("update.upToDate", { version: result.current }), "success");
      }
    } catch (error) {
      addNotification(t("update.unreachable", { reason: String(error) }), "error");
    } finally {
      setBusy(null);
    }
  }

  async function install() {
    setBusy("installing");
    try {
      const result = await updateApi.install();
      addNotification(result.message, result.installed ? "success" : "error");
      if (result.installed) setStatus(null);
    } catch (error) {
      addNotification(String(error), "error");
    } finally {
      setBusy(null);
    }
  }

  if (status?.can_install && status.latest) {
    return (
      <button
        type="button"
        onClick={install}
        disabled={busy !== null}
        className="flex items-center gap-1 text-xs text-primary hover:underline disabled:opacity-60"
      >
        <Download className="w-3.5 h-3.5" aria-hidden="true" />
        {busy === "installing"
          ? t("update.installing")
          : t("update.install", { latest: status.latest })}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={check}
      disabled={busy !== null}
      title={t("update.check")}
      aria-label={t("update.check")}
      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-60"
    >
      <RefreshCw
        className={busy === "checking" ? "w-3.5 h-3.5 animate-spin" : "w-3.5 h-3.5"}
        aria-hidden="true"
      />
      <span className="hidden lg:inline">
        {busy === "checking"
          ? t("update.checking")
          : status
            ? t("update.version", { version: status.current })
            : t("update.check")}
      </span>
    </button>
  );
}
