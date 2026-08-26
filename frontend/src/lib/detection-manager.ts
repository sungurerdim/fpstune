/**
 * DetectionManager - Singleton for coordinating setting detection.
 * Uses the new SettingExecutor architecture with parallel detection.
 *
 * Flow:
 * 1. Initialize store from /api/settings/definitions (mandatory)
 * 2. Detect settings via POST /api/settings/detect (parallel, no polling)
 * 3. Update store with detected values
 *
 * Key improvement: Single request for detection, no polling needed.
 * Backend handles parallel execution with per-setting timeouts.
 */

import { settingsApi } from "./api";
import type { DetectResponse } from "./api";
import { createLogger } from "./logger";
import { useStore } from "../store";
import type { DetectionResultUpdate } from "../store/settings";
import type { SettingCategory } from "../types/setting";

const log = createLogger("DetectionManager");

/** Derive active categories from the store's current settings — no hardcoded list. */
function getAllCategories(): SettingCategory[] {
  const store = useStore.getState();
  return Object.keys(store.categoryDetectionStatus);
}

class DetectionManager {
  private static instance: DetectionManager;
  private detectingCategories: Set<SettingCategory> = new Set();
  private initPromise: Promise<void> | null = null;
  private allDetectionPromise: Promise<void> | null = null;
  private allDetectionDone = false;
  private inflightRedetects: Map<string, Promise<void>> = new Map();

  private constructor() {}

  /**
   * The one path from a detect response into the store.
   *
   * Every caller finalises through here, because the copy that did not — the
   * post-apply re-detect — mapped four of the six fields and skipped the
   * version bump, so `recommended_value` and `original_value` were blanked and
   * eleven subscribers kept rendering the values from before the apply.
   */
  private static finalize(
    response: DetectResponse,
    doneCategories: SettingCategory[],
  ): void {
    const results: Record<string, DetectionResultUpdate> = {};
    for (const [id, result] of Object.entries(response.results)) {
      results[id] = {
        value: result.value,
        is_optimized: result.is_optimized,
        is_applicable: result.is_applicable,
        applicable_reason: result.applicable_reason,
        error: result.error,
        recommended_value: result.recommended_value,
        original_value: result.original_value,
      };
    }
    useStore.getState().finalizeDetection(results, doneCategories);
  }

  static getInstance(): DetectionManager {
    if (!DetectionManager.instance) {
      DetectionManager.instance = new DetectionManager();
    }
    return DetectionManager.instance;
  }

  /**
   * Initialize the store with definitions AND categories from API.
   * This is MANDATORY - must be called before starting detections.
   * Uses a promise to prevent duplicate initialization calls.
   */
  async initializeStore(): Promise<void> {
    const store = useStore.getState();

    // Return early if already initialized
    if (store.isInitialized()) {
      return;
    }

    // Reuse existing initialization if in progress
    if (this.initPromise) {
      return this.initPromise;
    }

    this.initPromise = (async () => {
      try {
        log.info("Fetching setting definitions and categories...");
        const [definitions, categories] = await Promise.all([
          settingsApi.getDefinitions(),
          settingsApi.getCategoriesMetadata(),
        ]);

        if (
          !definitions ||
          !Array.isArray(definitions) ||
          definitions.length === 0
        ) {
          throw new Error("Failed to load setting definitions from API");
        }

        store.initializeFromDefinitions(definitions, categories);
        log.info(
          `Store initialized with ${definitions.length} settings, ${categories?.length ?? 0} categories`,
        );
      } catch (error) {
        // Reset promise on error so retry is possible
        this.initPromise = null;
        throw error;
      }
    })();

    return this.initPromise;
  }

  /**
   * Detect all settings for a category.
   * Uses the new parallel detection API (single request, no polling).
   */
  async detectCategory(category: SettingCategory): Promise<void> {
    const store = useStore.getState();
    const status = store.categoryDetectionStatus[category];

    // Skip if already done or in progress
    if (status === "done") return;
    if (this.detectingCategories.has(category) || status === "loading") return;

    // Maintenance has no detection
    if (category === "maintenance") {
      store.setSettingsCategoryStatus(category, "done");
      return;
    }

    store.setSettingsCategoryStatus(category, "loading");
    this.detectingCategories.add(category);

    try {
      log.info(`Detecting ${category}...`);
      const response = await settingsApi.detect({ category });

      // `is_applicable` arrives decided. This used to be re-derived here by
      // checking for the literal "not_installed", in three places, because the
      // backend's sentinel list was missing that spelling — see
      // applicability.ABSENT_READINGS, which now owns the rule for all four.
      DetectionManager.finalize(response, [category]);
      log.info(
        `${category} detected in ${response.total_time_ms}ms (${response.success_count} success, ${response.error_count} errors)`,
      );
    } catch (error) {
      log.error(`Failed to detect ${category}:`, error);
      store.setSettingsCategoryStatus(category, "error");
    } finally {
      this.detectingCategories.delete(category);
    }
  }

  /**
   * Detect all settings at once.
   * Uses the new parallel detection API.
   * Uses a promise to prevent duplicate detection calls.
   */
  async detectAll(): Promise<void> {
    // Never re-run after first successful completion
    if (this.allDetectionDone) return;

    // Reuse existing detection if in progress
    if (this.allDetectionPromise) {
      return this.allDetectionPromise;
    }

    const store = useStore.getState();

    // Check if all categories are already done
    const allDone = getAllCategories().every(
      (cat) => store.categoryDetectionStatus[cat] === "done",
    );
    if (allDone) {
      this.allDetectionDone = true;
      return;
    }

    this.allDetectionPromise = (async () => {
      try {
        const categories = getAllCategories();

        // Mark maintenance as done immediately, rest as loading
        for (const category of categories) {
          if (category === "maintenance") {
            store.setSettingsCategoryStatus(category, "done");
          } else {
            store.setSettingsCategoryStatus(category, "loading");
            this.detectingCategories.add(category);
          }
        }

        const detectableCategories = categories.filter(
          (c) => c !== "maintenance",
        );

        log.info(
          `Detecting ${detectableCategories.length} categories in parallel...`,
        );

        // Detect each category independently — UI updates as each one finishes
        await Promise.all(
          detectableCategories.map(async (category) => {
            try {
              const response = await settingsApi.detect({ category });

              // Finalize this category immediately so the UI updates
              DetectionManager.finalize(response, [category]);
              log.info(
                `${category} detected in ${response.total_time_ms}ms (${response.success_count} ok, ${response.error_count} err)`,
              );
            } catch (err) {
              log.error(`Failed to detect ${category}:`, err);
              store.setSettingsCategoryStatus(category, "error");
            } finally {
              this.detectingCategories.delete(category);
            }
          }),
        );

        this.allDetectionDone = true;
        log.info("All categories detected.");
      } catch (error) {
        log.error("Failed to detect all settings:", error);
        for (const category of getAllCategories()) {
          if (store.categoryDetectionStatus[category] === "loading") {
            store.setSettingsCategoryStatus(category, "error");
          }
        }
      } finally {
        this.detectingCategories.clear();
        this.allDetectionPromise = null;
      }
    })();

    return this.allDetectionPromise;
  }

  /**
   * Re-detect specific settings.
   * Updates full detection state including isOptimized and isApplicable.
   * Deduplicates concurrent calls for the same setting ID set.
   */
  async redetectSettings(settingIds: string[]): Promise<void> {
    if (settingIds.length === 0) return;

    // Dedup: concurrent calls for the same IDs share one in-flight request
    const key = [...settingIds].sort().join(",");
    const inflight = this.inflightRedetects.get(key);
    if (inflight) return inflight;

    const promise = this._doRedetectSettings(settingIds).finally(() => {
      this.inflightRedetects.delete(key);
    });
    this.inflightRedetects.set(key, promise);
    return promise;
  }

  private async _doRedetectSettings(settingIds: string[]): Promise<void> {
    try {
      log.info(`Re-detecting ${settingIds.length} settings...`);
      const response = await settingsApi.detect({ setting_ids: settingIds });

      // No category finishes here — this re-detects a hand-picked set, so
      // marking one done would claim a full pass that did not happen.
      DetectionManager.finalize(response, []);

      log.info(
        `Re-detection complete: ${response.success_count} success, ${response.error_count} errors`,
      );
    } catch (error) {
      log.error("Failed to re-detect settings:", error);
    }
  }

  stopAll(): void {
    this.detectingCategories.clear();
  }
}

export const detectionManager = DetectionManager.getInstance();
