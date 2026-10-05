import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight } from "lucide-react";
import { useT } from "../../i18n";
import type { Setting } from "../../types/setting";
import { Card } from "../ui/Card";
import { TweakListRow } from "../TweakListRow";

/**
 * The already-optimal settings, behind a fold Home owns: the headline counts
 * them, and a count whose members cannot be listed is a claim.
 */
export function OptimizedFold({
  settings: optimized,
  categoryLabel,
}: {
  settings: Setting[];
  categoryLabel: (id: string) => string;
}) {
  const { t } = useT();
  const [showOptimized, setShowOptimized] = useState(false);
  if (optimized.length === 0) return null;
  return (
      <Card>
        <button
          onClick={() => setShowOptimized((open) => !open)}
          aria-expanded={showOptimized}
          className="w-full flex items-center gap-2 p-3 text-left hover:bg-muted/30 transition-colors"
        >
          {showOptimized ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
          <CheckCircle2 className="w-4 h-4 text-success" />
          <h2 className="font-semibold text-sm">
            {t("home.alreadyOptimized")}
          </h2>
          <span className="text-xs text-muted-foreground">
            {optimized.length}
          </span>
        </button>
        {showOptimized && (
          <div className="p-3 pt-0 grid grid-cols-1 gap-2 items-start xl:grid-cols-2 3xl:grid-cols-3">
            {optimized.map((s) => (
              <TweakListRow
                key={s.id}
                setting={s}
                categoryLabel={categoryLabel(s.category)}
              />
            ))}
          </div>
        )}
      </Card>
  );
}
