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
  return (
    <ConfirmDialog
      open={open}
      title="Restart Docker & WSL?"
      confirmLabel="Prune & compact"
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      Docker Desktop and all WSL distributions will be shut down and restarted so
      their virtual disk can be compacted and the space truly returned. This can
      take several minutes. Save your work first.
    </ConfirmDialog>
  );
}
