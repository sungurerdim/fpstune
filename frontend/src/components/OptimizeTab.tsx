/**
 * OptimizeTab — what is not optimized on this machine, and how to fix it.
 *
 * Three categories, closed until asked for, each saying "N of M not optimized"
 * on its own line: Software, Hardware, Games. Software opens to the backend's
 * categories, Hardware to the machine's devices (GPU, Monitor 1, Monitor 2,
 * adapters, drives), Games to one section per game; each of those opens to
 * one-line rows, the ones that need work first.
 *
 * The split is the backend's (`domain`), asked through `lib/tweakDomain.ts`, so
 * a row is in exactly one category; headings are the backend's words (C9), and
 * the order of rows is frozen once read (`useRowOrder`) so Apply never slides
 * the next row away. A search replaces the three categories with one flat list
 * of matches, because a match inside a closed section would be invisible.
 *
 * Only optimizing lives here. Measurements, health and cleanup have their own
 * tabs; notices about the app itself sit above the tab strip's panel.
 */

import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useT } from "../i18n";
import { localizedDescription, localizedName } from "../i18n/settings";
import { useApply } from "../hooks/useApply";
import { useRowOrder } from "../hooks/useRowOrder";
import { categoryGroups, gameGroups, partitionByDomain } from "../lib/tweakDomain";
import { isOptimizeRow, isTweakManual } from "../lib/tweakStatus";
import { useStore } from "../store";
import type { Setting } from "../types/setting";
import { CategoryApply } from "./CategoryApply";
import { CategorySection } from "./CategorySection";
import { api, type HardwareInfo } from "../lib/api";
import { AudioSection } from "./hardware/AudioSection";
import { DeviceList } from "./hardware/DeviceList";
import { listDevices, type DeviceDescriptor } from "./hardware/devices";
import { DisplaysAutoAllButton, MonitorCard } from "./hardware/MonitorCard";
import { NetworkAdapterCard } from "./hardware/NetworkAdapterCard";
import { StorageDriveCard } from "./hardware/StorageDriveCard";
import { useHardware } from "./hardware/useHardware";
import { useRefreshOnFocus } from "./hardware/useRefreshOnFocus";
import { SelectionToolbar } from "./SelectionToolbar";
import type { RowStatus } from "./TweakRow";
import { TweakRowList } from "./TweakRowList";

/** Does a row answer the search? Its names, in either language, and its description. */
function matches(setting: Setting, query: string): boolean {
  return [
    setting.displayName,
    setting.name,
    setting.description,
    localizedName(setting),
    localizedDescription(setting),
  ].some((text) => text.toLowerCase().includes(query));
}

/**
 * What an opened device offers besides its tweaks: the controls that belong to
 * the device itself rather than to a setting — switching a display mode,
 * reconnecting an adapter, running a drive's TRIM, an audio endpoint's switch.
 * A device with no controls of its own (CPU, memory, GPU, a component's shared
 * tweaks) has none: its header already names it, and its rows are the content.
 */
function deviceControls(device: DeviceDescriptor, hardware: HardwareInfo | null): ReactNode {
  const body = device.body;
  switch (body.type) {
    case "monitor":
      return (
        <>
          {body.index === 0 && (hardware?.monitors.length ?? 0) > 1 && (
            <DisplaysAutoAllButton monitors={hardware?.monitors ?? []} />
          )}
          <MonitorCard monitor={body.monitor} displayIndex={body.index} />
        </>
      );
    case "drive":
      return <StorageDriveCard drive={body.drive} />;
    case "adapter":
      return <NetworkAdapterCard adapter={body.adapter} />;
    case "audio":
      return <AudioSection devices={hardware?.audio_devices} loading={!hardware} />;
    case "cpu":
    case "memory":
    case "gpu":
    case "shared":
      return null;
  }
}

export function OptimizeTab() {
  const { t } = useT();
  const settingsMap = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const categories = useStore((s) => s.categories);
  const selectedSettingIds = useStore((s) => s.selectedSettingIds);
  const toggleSelectedSetting = useStore((s) => s.toggleSelectedSetting);
  const operationStatus = useStore((s) => s.operationStatus);
  const operationError = useStore((s) => s.operationError);
  const detecting = useStore((s) => s.isAnyCategoryLoading());
  const { apply, reset, pendingIds } = useApply();
  const { hardware } = useHardware();
  // A change made in a vendor tool is invisible until something re-reads;
  // coming back to the window is when to do that.
  useRefreshOnFocus();

  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();

  const rows = useMemo(
    () => [...settingsMap.values()].filter(isOptimizeRow),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
    [settingsMap, settingsVersion],
  );
  const compare = useRowOrder(rows);
  const inOrder = (list: readonly Setting[]) => [...list].sort(compare);

  const shown = useMemo(
    () => (needle ? rows.filter((s) => matches(s, needle)) : rows),
    [rows, needle],
  );
  const { software, hardware: hardwareRows, game } = useMemo(
    () => partitionByDomain(shown),
    [shown],
  );

  // Hardware rows no listed device claims (a monitor not enumerated yet, a
  // vendor's driver tweak before the inventory arrives) keep a plain list, so
  // no tweak drops off the page.
  const unclaimed = useMemo(() => {
    const devices = listDevices(hardware, t);
    return hardwareRows.filter((s) => !devices.some((d) => d.match?.(s)));
  }, [hardware, hardwareRows, t]);

  const statuses = useMemo(() => {
    const merged: Record<string, RowStatus> = { ...operationStatus };
    for (const id of pendingIds) merged[id] = "running";
    return merged;
  }, [operationStatus, pendingIds]);

  // Several checks read data Windows only hands to an elevated caller, and one
  // that read nothing is not a finding: its line says so, with the likeliest
  // reason the user can act on, rather than leaving a blank where a state goes.
  const isAdmin = useQuery({
    queryKey: ["system"],
    queryFn: api.getSystemInfo,
    staleTime: Infinity,
  }).data?.is_admin;
  const unreadNote = (setting: Setting): ReactNode => {
    if (!isTweakManual(setting) || setting.currentValue !== null || setting.status === "loading") {
      return null;
    }
    const text = setting.detectionError
      ? t("row.unreadReason", { reason: setting.detectionError })
      : isAdmin === false
        ? t("row.unreadNeedsAdmin")
        : t("row.unreadNoReason");
    return (
      <span className="min-w-0 max-w-[40%] truncate text-xs text-muted-foreground" title={text}>
        {text}
      </span>
    );
  };

  const rowProps = {
    rowNote: unreadNote,
    onApply: (setting: Setting, value: unknown) => void apply(setting, value),
    onReset: (setting: Setting) => void reset(setting),
    selectedIds: selectedSettingIds,
    onSelect: (setting: Setting) => toggleSelectedSetting(setting.id),
    statuses,
    errors: operationError,
  };

  const leaf = (id: string, title: string, settings: Setting[]) => (
    <CategorySection
      key={id}
      title={title}
      settings={inOrder(settings)}
      actions={<CategoryApply settings={settings} name={title} />}
      {...rowProps}
    />
  );

  // One of the three categories: a closed line with its count and its Apply,
  // opening to the groups it is made of. A function, not a component declared
  // here: a component defined inside render is a new type on every render, and
  // would close the section each time the page updates.
  const domain = (key: string, title: string, settings: readonly Setting[], groups: ReactNode) => (
    <CategorySection
      key={key}
      level={2}
      title={title}
      settings={settings}
      actions={<CategoryApply settings={settings} name={title} />}
      {...rowProps}
    >
      {groups}
    </CategorySection>
  );

  const nothing = <p className="px-2 py-1 text-xs text-muted-foreground">{t("bands.nothingToDo")}</p>;

  return (
    <div className="space-y-2 pb-16">
      <div className="relative max-w-xs">
        <Search
          className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <input
          type="search"
          placeholder={t("settings.searchPlaceholder")}
          aria-label={t("settings.search")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-md border border-border bg-muted py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground"
        />
      </div>

      {settingsMap.size === 0 ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded-md bg-muted" />
          ))}
        </div>
      ) : needle ? (
        shown.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("optimize.noMatch")}</p>
        ) : (
          <CategorySection
            key="results"
            title={t("optimize.results")}
            settings={inOrder(shown)}
            defaultOpen
            actions={<CategoryApply settings={shown} name={t("optimize.results")} />}
            {...rowProps}
          />
        )
      ) : (
        <>
          {domain(
            "software",
            t("optimize.software"),
            software,
            software.length === 0
              ? nothing
              : categoryGroups(software, categories).map((g) => leaf(g.id, g.label, g.settings)),
          )}

          {domain(
            "hardware",
            t("optimize.hardware"),
            hardwareRows,
            <>
              <DeviceList
                hardware={hardware}
                renderBody={(device) => deviceControls(device, hardware)}
                renderRows={(_device, list) => (
                  <TweakRowList settings={inOrder(list)} {...rowProps} />
                )}
              />
              {unclaimed.length > 0 && leaf("other-hardware", t("optimize.otherHardware"), unclaimed)}
            </>,
          )}

          {domain(
            "games",
            t("optimize.games"),
            game,
            game.length === 0 ? (
              <p className="px-2 py-1 text-xs text-muted-foreground">
                {detecting ? t("games.reading") : t("games.noneFound")}
              </p>
            ) : (
              gameGroups(game).map((g) => leaf(g.id, g.label, g.settings))
            ),
          )}
        </>
      )}

      {/* The scope buttons act on exactly the rows in view; ticked rows get
          their own apply / reset beside them. */}
      <SelectionToolbar settings={shown} name={t("tab.optimize")} />
    </div>
  );
}
