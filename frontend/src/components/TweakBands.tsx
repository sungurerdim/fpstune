import { useState } from "react";
import { ChevronDown, ChevronRight, CircleCheck } from "lucide-react";
import { useT } from "../i18n";
import { TweakRows, type TweakRow } from "./TweakRows";

/**
 * The one drawing of "needs action" and "already ideal", for every surface.
 *
 * Rows that need something come first and are always open; rows already at
 * their ideal value sit behind one fold, collapsed, so a long list of finished
 * work never drowns what is left. Advisories stay with the rows that need
 * action — fpstune cannot write them, and the row says where to go instead.
 * Bulk buttons are not here: they belong to the scope's header (`ScopeActions`),
 * so a band never carries a second, differently-counted copy of them.
 */
export function TweakBands({ rows }: { rows: readonly TweakRow[] }) {
  const { t } = useT();
  const [showIdeal, setShowIdeal] = useState(false);
  const needs = rows.filter((r) => !r.setting.isOptimized);
  const ideal = rows.filter((r) => r.setting.isOptimized);

  return (
    <div className="space-y-2">
      {needs.length > 0 ? (
        <TweakRows rows={needs} />
      ) : (
        <p className="flex items-center gap-1.5 text-xs text-success">
          <CircleCheck className="h-3.5 w-3.5" aria-hidden />
          {t("bands.nothingToDo")}
        </p>
      )}
      {ideal.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setShowIdeal(!showIdeal)}
            aria-expanded={showIdeal}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            {showIdeal ? (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden />
            )}
            {t(showIdeal ? "bands.hideIdeal" : "bands.showIdeal", { count: ideal.length })}
          </button>
          {showIdeal && <TweakRows rows={ideal} />}
        </>
      )}
    </div>
  );
}
