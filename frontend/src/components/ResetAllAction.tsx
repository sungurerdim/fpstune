import { useT } from "../i18n";
import { useMemo, useState } from "react";
import { RotateCcw, Loader2 } from "lucide-react";
import { useStore } from "../store";
import { cn } from "../lib/utils";
import { useBulkStream } from "../hooks/useBulkStream";
import { valuesEqual, type Setting } from "../types/setting";
import { ConfirmDialog } from "./ui/ConfirmDialog";

/**
 * "Reset to Defaults" across every applicable tweak, for the Software Tweaks tab.
 *
 * Applying is deliberately NOT here: the band's own button applies, scoped to
 * the rows the user can see. This one stays global because "put everything
 * back" has no useful narrower meaning — and because it touches everything, it
 * asks first, then runs through the same streamed reset as a selection, so
 * every row shows its own outcome and Stop works.
 */
export function ResetAllAction() {
  const { t } = useT();
  const settingsMap = useStore((state) => state.settings);
  const settingsVersion = useStore((state) => state._settingsVersion);
  const isDetecting = useStore((state) => state.isAnyCategoryLoading());
  const { run, isRunning } = useBulkStream();
  const [confirming, setConfirming] = useState(false);

  const settingsToReset = useMemo(() => {
    const rows: Setting[] = [];
    for (const s of settingsMap.values()) {
      if (!s.isApplicable || s.isAction || s.currentValue === null || s.isReadonly)
        continue;
      if (!valuesEqual(s.currentValue, s.defaultValue)) rows.push(s);
    }
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settingsMap, settingsVersion]);

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <ConfirmDialog
        open={confirming}
        title={t("resetAll.title", { count: settingsToReset.length })}
        confirmLabel={t("resetAll.confirm")}
        onConfirm={() => {
          setConfirming(false);
          run(
            "reset",
            settingsToReset.map((s) => s.id),
          );
        }}
        onCancel={() => setConfirming(false)}
      >
        {t("resetAll.body")}
      </ConfirmDialog>
      {isDetecting && (
        <span className="text-xs text-muted-foreground flex items-center gap-1">
          <Loader2 className="w-3 h-3 animate-spin" /> {t("resetAll.detecting")}
        </span>
      )}
      <button
        type="button"
        onClick={() => setConfirming(true)}
        disabled={isRunning || settingsToReset.length === 0}
        className={cn(
          "px-3 py-1.5 text-xs rounded-md flex items-center gap-1.5 font-medium transition-colors",
          settingsToReset.length === 0
            ? "bg-muted text-muted-foreground/50 cursor-not-allowed"
            : "bg-muted hover:bg-muted/80 text-foreground",
        )}
      >
        {isRunning ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : (
          <RotateCcw className="w-3 h-3" />
        )}
        {t("toolbar.resetToDefaults", { count: settingsToReset.length })}
      </button>
    </div>
  );
}
