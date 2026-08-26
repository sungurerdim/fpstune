/**
 * Settings state slice for Zustand store.
 *
 * Flat Map<SettingId, Setting> keyed by the backend's own id, so a detection
 * result can be applied without knowing which category or module it came from.
 */

import type { StateCreator } from "zustand";
import type {
  Setting,
  SettingId,
  SettingCategory,
  SettingDefinition,
  CategoryMetadata,
  CategoryMetadataResponse,
} from "../types/setting";
import {
  definitionToSetting,
  categoryResponseToMetadata,
} from "../types/setting";

// Category status for detection tracking
export type CategoryDetectionStatus = "idle" | "loading" | "done" | "error";

// Derive UI status from a detection result's isOptimized flag + raw value.
// "default" when value is null/unknown (setting at OS default, not yet diverged).
function computeStatusFromResult(
  isOptimized: boolean,
  value: unknown,
): Setting["status"] {
  if (isOptimized) return "optimal";
  if (
    value === null ||
    (typeof value === "string" && value.toLowerCase() === "unknown")
  ) {
    return "default";
  }
  return "suboptimal";
}

/**
 * One setting's detection outcome, in the backend's own field spelling.
 *
 * Named rather than inlined because the detect route, the re-detect path and the
 * cleanup sizer all build it: three inline copies is how one of them came to omit
 * `recommended_value` and `original_value` and silently blank both.
 */
export interface DetectionResultUpdate {
  value: unknown;
  is_optimized: boolean;
  is_applicable: boolean;
  applicable_reason?: string;
  // Detection failure for this setting; absent = the caller has no news about
  // it (a post-apply single update), null = detection ran clean.
  error?: string | null;
  recommended_value?: unknown;
  original_value?: unknown;
}

export interface SettingsSlice {
  // === Primary Data ===
  // Flat Map for O(1) access by ID
  settings: Map<SettingId, Setting>;
  // Category metadata from backend (SSOT)
  categories: Map<string, CategoryMetadata>;
  /**
   * Bumped by every write to `settings`.
   *
   * Eleven components subscribe to this and to nothing else about the Map, so a
   * mutator that replaces `settings` without bumping it leaves all eleven
   * rendering pre-change values. That is not a render optimisation to be traded
   * away — it is the only signal they get.
   */
  _settingsVersion: number;

  // === Detection State ===
  categoryDetectionStatus: Record<string, CategoryDetectionStatus>;

  // === Initialization ===
  initializeFromDefinitions: (
    definitions: SettingDefinition[],
    categoryMetadata?: CategoryMetadataResponse[],
  ) => void;
  isInitialized: () => boolean;

  // === Detection Results ===
  setSettingsCategoryStatus: (
    category: SettingCategory,
    status: CategoryDetectionStatus,
  ) => void;
  setSettingDetectionResult: (
    id: SettingId,
    value: unknown,
    isOptimized: boolean,
    isApplicable: boolean,
    applicableReason?: string,
  ) => void;

  // === Atomic Detection Finalization ===
  // Single set() call: updates all detection results + marks categories done atomically.
  // Prevents intermediate renders where setting values are updated but categories still show "loading".
  finalizeDetection: (
    results: Record<string, DetectionResultUpdate>,
    doneCategories: string[],
  ) => void;

  // === Selectors ===
  isAnyCategoryLoading: () => boolean;
}

// Empty initial state — dynamically populated from backend definitions
const initialCategoryStatus: Record<string, CategoryDetectionStatus> = {};

export const createSettingsSlice: StateCreator<
  SettingsSlice,
  [],
  [],
  SettingsSlice
> = (set, get) => ({
  settings: new Map(),
  categories: new Map(),
  categoryDetectionStatus: { ...initialCategoryStatus },
  // Version counter to force re-renders when Maps change
  _settingsVersion: 0,

  // Initialize store with definitions and category metadata from API
  initializeFromDefinitions: (definitions, categoryMetadata) => {
    const newSettings = new Map<SettingId, Setting>();
    const newCategories = new Map<string, CategoryMetadata>();

    // Process category metadata if provided
    if (categoryMetadata) {
      for (const cat of categoryMetadata) {
        const metadata = categoryResponseToMetadata(cat);
        newCategories.set(metadata.id, metadata);
      }
    }

    // Process settings
    for (const def of definitions) {
      const setting = definitionToSetting(def);
      newSettings.set(setting.id, setting);
    }

    // Build dynamic category detection status from actual categories
    const dynamicCategoryStatus: Record<string, CategoryDetectionStatus> = {};
    for (const setting of newSettings.values()) {
      if (!dynamicCategoryStatus[setting.category]) {
        dynamicCategoryStatus[setting.category] = "idle";
      }
    }

    set((state) => ({
      settings: newSettings,
      categories: newCategories,
      categoryDetectionStatus: dynamicCategoryStatus,
      _settingsVersion: state._settingsVersion + 1,
    }));
  },

  isInitialized: () => get().settings.size > 0,

  setSettingsCategoryStatus: (category, status) => {
    set({
      categoryDetectionStatus: {
        ...get().categoryDetectionStatus,
        [category]: status,
      },
    });
  },

  // One setting's result is the same write as many, so it takes the same path:
  // a second implementation is what let a single-setting update skip the
  // version bump that every reader of the Map depends on.
  setSettingDetectionResult: (
    id,
    value,
    isOptimized,
    isApplicable,
    applicableReason,
  ) => {
    get().finalizeDetection(
      {
        [id]: {
          value,
          is_optimized: isOptimized,
          is_applicable: isApplicable,
          applicable_reason: applicableReason,
        },
      },
      [],
    );
  },

  // Atomic finalization: updates all detection results + marks categories done in one set() call.
  finalizeDetection: (results, doneCategories) => {
    const settings = get().settings;
    const newSettings = new Map(settings);

    for (const [settingId, result] of Object.entries(results)) {
      const setting = newSettings.get(settingId as SettingId);
      if (setting) {
        const updatedSetting: Setting = {
          ...setting,
          currentValue: result.value,
          isOptimized: result.is_optimized,
          isApplicable: result.is_applicable,
          applicableReason: result.applicable_reason,
          ...(result.error !== undefined && {
            detectionError: result.error ?? undefined,
          }),
          ...(result.recommended_value !== undefined && {
            recommendedValue: result.recommended_value,
          }),
          // What the machine held when fpstune first saw this setting. The
          // backend owns it — it is persisted across runs, so a value recorded
          // in an earlier session survives a restart, which a store-local copy
          // never could. null means nothing was recorded, i.e. nothing to undo.
          //
          // Absent is not null: a caller that does not carry the field (a
          // post-apply single-setting update) must leave the recorded original
          // standing rather than erase what only a full scan records.
          ...(result.original_value !== undefined && {
            originalValue: result.original_value ?? undefined,
          }),
          status: computeStatusFromResult(result.is_optimized, result.value),
        };
        newSettings.set(settingId as SettingId, updatedSetting);
      }
    }

    const newCategoryStatus =
      doneCategories.length > 0
        ? { ...get().categoryDetectionStatus }
        : get().categoryDetectionStatus;
    for (const cat of doneCategories) {
      newCategoryStatus[cat] = "done";
    }

    set({
      settings: newSettings,
      categoryDetectionStatus: newCategoryStatus,
      _settingsVersion: get()._settingsVersion + 1,
    });
  },

  // === Selectors ===

  isAnyCategoryLoading: () =>
    Object.values(get().categoryDetectionStatus).some((s) => s === "loading"),
});
