import { TabNavigation } from "./components/TabNavigation";
import { OptimizeTab } from "./components/OptimizeTab";
import { DiskCleanupTab } from "./components/DiskCleanupTab";
import { BenchmarksTab } from "./components/BenchmarksTab";
import { CleanupRunnerProvider } from "./components/CleanupRunnerProvider";
import { NotificationToasts } from "./components/ui/NotificationToasts";
import { DisplayModeConfirm } from "./components/DisplayModeConfirm";
import { DetectionNotice } from "./components/DetectionNotice";
import { FirstRunNotice } from "./components/FirstRunNotice";
import { OsUpdateNotice } from "./components/OsUpdateNotice";
import { SelfCheckNotice } from "./components/SelfCheckNotice";
import { tabButtonId, tabPanelId } from "./components/ui/tabIds";
import { useStore } from "./store";

function App() {
  const activeTab = useStore((state) => state.activeTab);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Headless: cleanup size polling + freed-space resolution, on every tab */}
      <CleanupRunnerProvider />

      {/* Mounted once, above the tabs, so its live regions exist before the
          first message does — and so a notification raised on one tab is not
          lost by navigating to another. */}
      <NotificationToasts />
      {/* Asks "keep the new display mode?" for any monitor fpstune switched. */}
      <DisplayModeConfirm />

      {/* Tab Navigation (also hosts the app chrome: brand, activity, admin) */}
      <TabNavigation />

      {/* Tab Content — one panel at a time, named by the tab that selected it.
          Not focusable itself: every panel here contains focusable controls, so
          a tabindex on the wrapper would only add a stop that reads as nothing. */}
      <main
        data-testid="app-shell"
        className="flex-1 max-w-7xl 2xl:max-w-[120rem] 3xl:max-w-[150rem] mx-auto w-full px-6 py-4 pb-8"
      >
        {/* Facts about the app and the machine, not about one tab, stated once
            above the panel and each absent when there is nothing to say: the
            welcome (until dismissed), a Windows update since the last run, a
            detector two independent sources disagree on, and settings that
            could not be read. */}
        <FirstRunNotice />
        <OsUpdateNotice />
        <SelfCheckNotice />
        <DetectionNotice />
        <div
          role="tabpanel"
          id={tabPanelId(activeTab)}
          aria-labelledby={tabButtonId(activeTab)}
        >
          {activeTab === "optimize" && <OptimizeTab />}
          {activeTab === "cleanup" && <DiskCleanupTab />}
          {activeTab === "measure" && <BenchmarksTab />}
        </div>
      </main>
    </div>
  );
}

export default App;
