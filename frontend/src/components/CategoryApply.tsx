/**
 * CategoryApply — a category header's bulk action: "Apply (N)", N being the
 * tweaks in that category the backend says are not optimized.
 *
 * It is the header's one button. Reset to default is for the checked rows (the
 * bar at the foot of the page), so a header never carries two buttons whose
 * difference is a word. With nothing to apply it draws nothing at all: a
 * category that is right needs no control, and the count beside its name says so.
 */

import { useMemo, useState } from "react";
import { Zap } from "lucide-react";
import { useT } from "../i18n";
import { useApply } from "../hooks/useApply";
import { scopeTargets } from "../lib/bulkStream";
import type { Setting } from "../types/setting";
import { BulkConfirm, type Pending } from "./SelectionToolbar";
import { Button } from "./ui/Button";

export function CategoryApply({
  settings,
  name,
}: {
  settings: readonly Setting[];
  /** The scope in words ("Network", "Software"), for the accessible name and the question. */
  name: string;
}) {
  const { t } = useT();
  const { run, isRunning } = useApply();
  const targets = useMemo(() => scopeTargets(settings).apply, [settings]);
  const [pending, setPending] = useState<Pending | null>(null);

  if (targets.length === 0) return null;

  return (
    <>
      <Button
        size="xs"
        variant="warning"
        disabled={isRunning}
        icon={<Zap className="h-3.5 w-3.5" aria-hidden />}
        aria-label={t("actions.aria.apply", { count: targets.length, name })}
        title={t("actions.aria.apply", { count: targets.length, name })}
        onClick={() => setPending({ action: "apply", targets, scopeName: name })}
      >
        {t("actions.apply", { count: targets.length })}
      </Button>
      <BulkConfirm
        pending={pending}
        onConfirm={() => {
          if (pending) {
            run(
              pending.action,
              pending.targets.map((s) => s.id),
            );
          }
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      />
    </>
  );
}
