import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useT } from "../i18n";
import { api, errorMessage } from "../lib/api";
import { useStore } from "../store";
import { ConfirmDialog } from "./ui/ConfirmDialog";

/**
 * "Keep the new display mode?" — for every display mode fpstune writes.
 *
 * A mode change goes back on its own unless it is kept (`settings.display_mode`),
 * so a mode the panel cannot show leaves a black screen for fifteen seconds, not
 * for good. The per-monitor settings change modes from anywhere — a row, Home's
 * bulk apply, a streamed run — so the question is asked here, once, for every
 * pending display, rather than by each surface that might have caused one.
 *
 * While anything is running it checks every second, so the question appears
 * inside the revert window even in the middle of a long bulk run.
 */
export function DisplayModeConfirm() {
  const { t } = useT();
  const queryClient = useQueryClient();
  const busy = useStore((s) => s.busyOperations > 0 || s.bulkRun !== null);
  const [dismissed, setDismissed] = useState<string>("");

  const { data } = useQuery({
    queryKey: ["display-pending"],
    queryFn: api.getPendingDisplayChanges,
    // Every second while something runs or a mode waits: the count shown is the
    // backend's own time left, so a dialog that opens late is never optimistic.
    refetchInterval: (query) =>
      busy || (query.state.data?.devices.length ?? 0) > 0 ? 1000 : false,
  });

  const devices = data?.devices ?? [];
  const signature = devices.join("|");
  const open = devices.length > 0 && signature !== dismissed;

  const keep = async () => {
    setDismissed(signature);
    try {
      await api.keepAllDisplayChanges();
    } catch (error) {
      useStore.getState().addNotification(errorMessage(error), "warning");
    }
    void queryClient.invalidateQueries({ queryKey: ["display-pending"] });
  };

  return (
    <ConfirmDialog
      open={open}
      title={t("displayConfirm.title")}
      confirmLabel={t("displayConfirm.keep")}
      cancelLabel={t("displayConfirm.dontKeep")}
      onConfirm={() => void keep()}
      onCancel={() => setDismissed(signature)}
    >
      {t("displayConfirm.body", { count: devices.length, seconds: data?.seconds_left ?? 0 })}
    </ConfirmDialog>
  );
}
