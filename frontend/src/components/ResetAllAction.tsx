import { useMemo } from "react";
import { RotateCcw, Loader2 } from "lucide-react";
import { useStore } from "../store";
import { cn } from "../lib/utils";
import { useBulkApply } from "../hooks/useBulkApply";
import { valuesEqual, type Setting } from "../types/setting";

/**
 * "Reset to Defaults" across every applicable tweak, for the Software Tweaks tab.
 *
 * Applying is deliberately NOT here. It used to be — a global "Optimize All (N)"
 * sat next to a per-band "Fix all", two buttons for one action whose counts could
 * differ the moment a filter was on. The band's button is the apply, because it is
 * scoped to the rows the user can actually see; this one stays global because
 * "put everything back" has no useful narrower meaning.
 */
export function ResetAllAction() {
  const settingsMap = useStore((state) => state.settings);
  const settingsVersion = useStore((state) => state._settingsVersion);
  const isDetecting = useStore((state) => state.isAnyCategoryLoading());
  const { apply, isApplying, lastResult } = useBulkApply();

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

  const resetAll = () => {
    const payload: Record<string, unknown> = {};
    for (const s of settingsToReset) payload[s.id] = s.defaultValue;
    if (Object.keys(payload).length > 0) apply(payload);
  };

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {isDetecting && (
        <span className="text-xs text-muted-foreground flex items-center gap-1">
          <Loader2 className="w-3 h-3 animate-spin" /> Detecting...
        </span>
      )}
      {lastResult && (
        <span className="text-xs text-muted-foreground">
          {lastResult.success} reset
          {lastResult.error > 0 && (
            <span className="text-destructive"> · {lastResult.error} failed</span>
          )}
        </span>
      )}
      <button
        type="button"
        onClick={resetAll}
        disabled={isApplying || settingsToReset.length === 0}
        className={cn(
          "px-3 py-1.5 text-xs rounded-md flex items-center gap-1.5 font-medium transition-colors",
          settingsToReset.length === 0
            ? "bg-muted text-muted-foreground/50 cursor-not-allowed"
            : "bg-muted hover:bg-muted/80 text-foreground",
        )}
      >
        {isApplying ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : (
          <RotateCcw className="w-3 h-3" />
        )}
        Reset to Defaults ({settingsToReset.length})
      </button>
    </div>
  );
}
