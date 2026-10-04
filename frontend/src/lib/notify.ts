import { useStore } from "../store";

/** Report a failed hardware action through the one accessible toast channel. */
export function notifyError(message: string): void {
  useStore.getState().addNotification(message, "error");
}
