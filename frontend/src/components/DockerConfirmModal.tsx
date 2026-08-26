import { useT } from "../i18n";
import { ConfirmDialog } from "./ui/ConfirmDialog";

/**
 * Confirm gate for Docker prune runs. Pruning then compacts the WSL2 vhdx, which
 * requires shutting down Docker Desktop and every WSL distribution first — so we
 * warn before doing it.
 */
export function DockerConfirmModal({
  open,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useT();
  return (
    <ConfirmDialog
      open={open}
      title={t("docker.title")}
      confirmLabel={t("docker.confirm")}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      {t("docker.body")}
    </ConfirmDialog>
  );
}
