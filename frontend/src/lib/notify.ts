import { useStore } from "../store";

/** Report a failed hardware action through the one accessible toast channel. */
export function notifyError(message: string): void {
  useStore.getState().addNotification(message, "error");
}

/** Tell the user something about a hardware action that succeeded. */
export function notifyInfo(message: string): void {
  useStore.getState().addNotification(message, "info");
}
