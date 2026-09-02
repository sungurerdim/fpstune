import { create } from "zustand";
import type { SuiteRun } from "../lib/api";
import { createSettingsSlice, type SettingsSlice } from "./settings";

// "maintenance" was its own tab for two checkboxes (SFC and DISM), while Disk
// Cleanup already drove the same action runner. The repair panel moved there and
// the tab is gone; nothing persists the active tab, so no stored value can point
// at a route that no longer exists.
export type TabId =
  "home" | "settings" | "hardware" | "games" | "cleanup" | "benchmarks";
export type OperationStatus = "queued" | "running" | "verified" | "failed";

/** Outcome of a single cleanup/maintenance action for the results summary. */
export interface CleanupResult {
  id: string;
  name: string;
  success: boolean;
  /** True if this op reports a reclaimable size (cleanup); false for sizeless
   *  maintenance ops (sfc/dism/...), which show "Done" instead of freed space. */
  sized: boolean;
  /** Actual freed space in MB (before − after size); null while recomputing. */
  freedMB: number | null;
  error?: string;
}

interface AppSlice {
  // Selection mode
  selectedSettingIds: Set<string>;
  toggleSelectedSetting: (id: string) => void;
  selectSettingIds: (ids: string[]) => void;
  clearSelection: () => void;

  // Per-setting operation status during bulk SSE ops
  operationStatus: Record<string, OperationStatus>;
  setOperationStatus: (id: string, status: OperationStatus) => void;
  clearOperationStatus: () => void;

  // Cleanup/maintenance run results (keyed by setting id) for the summary panel
  cleanupResults: Record<string, CleanupResult>;
  recordCleanupResults: (results: CleanupResult[]) => void;

  // The last before/after the measurement suite took, so the Verify panel can
  // judge the settings' claims against it. Verify used to collect its own pair
  // from two instruments through its own buttons, which meant measuring the
  // machine twice to answer two questions about one change.
  suiteBefore: SuiteRun | null;
  suiteAfter: SuiteRun | null;
  setSuiteRun: (label: "before" | "after", run: SuiteRun | null) => void;

  // Maintenance tab: action ids selected across all cleanup/maintenance panels.
  // Drives the single unified "Run Cleanup" button in the top band.
  maintenanceSelection: Record<string, boolean>;
  toggleMaintenanceSelection: (id: string) => void;
  setMaintenanceSelection: (ids: string[], selected: boolean) => void;
  clearMaintenanceSelection: () => void;

  // Tab navigation
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;

  /**
   * True while the app is changing the machine: a single apply, a bulk run, a
   * cleanup. Anything that competes for the same PowerShell — the hardware
   * re-read on window focus, above all — asks this first.
   *
   * Counter-backed rather than a bare boolean, because these overlap: a bulk
   * run finishing while a cleanup is still going must not report the machine
   * idle. Was a boolean nothing ever set, so every reader of it was reading a
   * constant false.
   */
  isApplying: boolean;
  busyOperations: number;
  beginOperation: () => void;
  endOperation: () => void;

  /**
   * Errors the app has decided the user must be told about.
   *
   * Oldest-first, capped at MAX_NOTIFICATIONS. Producers are "cannot reach the
   * backend" (main.tsx) and the cleanup failures (useCleanupRunner) — both are
   * conditions the user can act on, so dropping one silently is not an option
   * the cap is allowed to take. It bounds a session that never renders them
   * rather than choosing which to lose in one that does.
   */
  notifications: Notification[];
  addNotification: (message: string, type: Notification["type"]) => void;
  removeNotification: (id: string) => void;
}

export interface Notification {
  id: string;
  message: string;
  type: "success" | "error" | "warning" | "info";
}

/**
 * Enough to hold every distinct failure one cleanup run can produce, and few
 * enough that an app left open overnight retrying an unreachable backend cannot
 * grow the array without limit.
 */
const MAX_NOTIFICATIONS = 50;

/**
 * `Date.now()` was the id, and two notifications raised in the same millisecond
 * — which a bulk cleanup does routinely — collided, so removing either removed
 * both. A counter cannot collide within a session, which is the only scope
 * these ids ever cross.
 */
let notificationSequence = 0;

// Combined store type
type FpstuneStore = AppSlice & SettingsSlice;

export const useStore = create<FpstuneStore>()((...args) => {
  const [set] = args;

  return {
    // App slice
    selectedSettingIds: new Set<string>(),
    toggleSelectedSetting: (id) =>
      set((state) => {
        const next = new Set(state.selectedSettingIds);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return { selectedSettingIds: next };
      }),
    selectSettingIds: (ids) =>
      set((state) => {
        const next = new Set(state.selectedSettingIds);
        ids.forEach((id) => next.add(id));
        return { selectedSettingIds: next };
      }),
    clearSelection: () =>
      set({ selectedSettingIds: new Set<string>(), operationStatus: {} }),

    operationStatus: {},
    setOperationStatus: (id, status) =>
      set((state) => ({
        operationStatus: { ...state.operationStatus, [id]: status },
      })),
    clearOperationStatus: () => set({ operationStatus: {} }),

    cleanupResults: {},
    recordCleanupResults: (results) =>
      set((state) => {
        const next = { ...state.cleanupResults };
        for (const r of results) next[r.id] = r;
        return { cleanupResults: next };
      }),

    suiteBefore: null,
    suiteAfter: null,
    setSuiteRun: (label, run) =>
      set(label === "before" ? { suiteBefore: run } : { suiteAfter: run }),

    maintenanceSelection: {},
    toggleMaintenanceSelection: (id) =>
      set((state) => ({
        maintenanceSelection: {
          ...state.maintenanceSelection,
          [id]: !state.maintenanceSelection[id],
        },
      })),
    // Set many at once, because a group header's checkbox is one decision over a
    // whole group: toggling each id in turn would flip the ones already selected
    // back off and select the rest, which is the opposite of "select all".
    setMaintenanceSelection: (ids, selected) =>
      set((state) => {
        const next = { ...state.maintenanceSelection };
        for (const id of ids) next[id] = selected;
        return { maintenanceSelection: next };
      }),
    clearMaintenanceSelection: () => set({ maintenanceSelection: {} }),

    activeTab: "home",
    setActiveTab: (tab) => set({ activeTab: tab }),

    isApplying: false,
    busyOperations: 0,
    beginOperation: () =>
      set((state) => ({
        busyOperations: state.busyOperations + 1,
        isApplying: true,
      })),
    endOperation: () =>
      set((state) => {
        // Never below zero: an unbalanced end would otherwise make the next
        // begin fail to register.
        const busyOperations = Math.max(0, state.busyOperations - 1);
        return { busyOperations, isApplying: busyOperations > 0 };
      }),

    notifications: [],
    addNotification: (message, type) =>
      set((state) => ({
        notifications: [
          ...state.notifications,
          { id: `n${++notificationSequence}`, message, type },
        ].slice(-MAX_NOTIFICATIONS),
      })),
    removeNotification: (id) =>
      set((state) => ({
        notifications: state.notifications.filter((n) => n.id !== id),
      })),

    // Settings slice (centralized architecture)
    ...createSettingsSlice(...args),
  };
});
