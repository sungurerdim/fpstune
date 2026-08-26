import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Settings, type LucideIcon } from "lucide-react";
import * as LucideIcons from "lucide-react";
import { TabNavigation } from "./components/TabNavigation";
import { HomeTab } from "./components/HomeTab";
import { SettingsTab } from "./components/SettingsTab";
import { DiskCleanupTab } from "./components/DiskCleanupTab";
import { HardwareTab } from "./components/HardwareTab";
import { GameTweaksTab } from "./components/GameTweaksTab";
import { BenchmarksTab } from "./components/BenchmarksTab";
import { CleanupRunnerProvider } from "./components/CleanupRunnerProvider";
import { NotificationToasts } from "./components/ui/NotificationToasts";
import { tabButtonId, tabPanelId } from "./components/ui/tabIds";
import { settingsApi } from "./lib/api";
import { useStore } from "./store";
import type {
  Setting,
  CategoryMetadata,
  ModuleMetadata,
} from "./types/setting";
import { moduleResponseToMetadata } from "./types/setting";

/**
 * Get Lucide icon component by name
 * Falls back to Settings icon if not found
 */
function getIconByName(name: string): LucideIcon {
  const icons = LucideIcons as unknown as Record<string, LucideIcon>;
  return icons[name] ?? Settings;
}

function App() {
  // Module metadata from backend (SSOT)
  const { data: moduleMetadataRaw } = useQuery({
    queryKey: ["modules-metadata"],
    queryFn: settingsApi.getModulesMetadata,
    staleTime: Infinity,
  });

  // Build lookup map for module metadata
  const moduleMetaMap = useMemo(() => {
    const map = new Map<string, ModuleMetadata>();
    if (moduleMetadataRaw) {
      for (const raw of moduleMetadataRaw) {
        map.set(raw.id, moduleResponseToMetadata(raw));
      }
    }
    return map;
  }, [moduleMetadataRaw]);

  // Store is initialized by DetectionManager in main.tsx before App renders
  const isStoreInitialized = useStore((state) => state.settings.size > 0);
  const definitionsLoading = !isStoreInitialized;

  // Get raw data from store
  const settings = useStore((state) => state.settings);
  const categories = useStore((state) => state.categories);
  const settingsVersion = useStore((state) => state._settingsVersion);
  const gpuCategoryStatus = useStore(
    (state) => state.categoryDetectionStatus.gpu,
  );
  const activeTab = useStore((state) => state.activeTab);

  // Compute categories with settings
  const categoriesWithSettings = useMemo(() => {
    const settingsArray = Array.from(settings.values());

    const settingsByCategory = new Map<string, Setting[]>();
    for (const setting of settingsArray) {
      if (!setting.isApplicable) continue;
      const categorySettings = settingsByCategory.get(setting.category) || [];
      categorySettings.push(setting);
      settingsByCategory.set(setting.category, categorySettings);
    }

    const result: Array<{ category: CategoryMetadata; settings: Setting[] }> =
      [];

    for (const [categoryId, categorySettings] of settingsByCategory) {
      const categoryMeta = categories.get(categoryId);
      if (categoryMeta && categorySettings.length > 0) {
        categorySettings.sort((a, b) => a.categoryOrder - b.categoryOrder);
        result.push({ category: categoryMeta, settings: categorySettings });
      }
    }

    result.sort((a, b) => a.category.order - b.category.order);
    return result;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion used for cache busting
  }, [settings, categories, settingsVersion]);

  // Check if GPU settings exist
  const hasGpuSettings = useMemo(() => {
    for (const { category, settings } of categoriesWithSettings) {
      if (category.id === "gpu" && settings.length > 0) return true;
    }
    return false;
  }, [categoriesWithSettings]);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Headless: cleanup size polling + freed-space resolution, on every tab */}
      <CleanupRunnerProvider />

      {/* Mounted once, above the tabs, so its live regions exist before the
          first message does — and so a notification raised on one tab is not
          lost by navigating to another. */}
      <NotificationToasts />

      {/* Tab Navigation (also hosts the app chrome: brand, activity, admin) */}
      <TabNavigation />

      {/* Tab Content — one panel at a time, named by the tab that selected it.
          Not focusable itself: every panel here contains focusable controls, so
          a tabindex on the wrapper would only add a stop that reads as nothing. */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-4 pb-8">
        <div
          role="tabpanel"
          id={tabPanelId(activeTab)}
          aria-labelledby={tabButtonId(activeTab)}
        >
          {activeTab === "home" && <HomeTab />}
          {activeTab === "settings" && (
            <SettingsTab
              categoriesWithSettings={categoriesWithSettings}
              moduleMetaMap={moduleMetaMap}
              definitionsLoading={definitionsLoading}
              gpuCategoryStatus={gpuCategoryStatus}
              hasGpuSettings={hasGpuSettings}
              getIconByName={getIconByName}
            />
          )}
          {activeTab === "games" && <GameTweaksTab />}
          {activeTab === "cleanup" && <DiskCleanupTab />}
          {activeTab === "hardware" && <HardwareTab />}
          {activeTab === "benchmarks" && <BenchmarksTab />}
        </div>
      </main>
    </div>
  );
}

export default App;
