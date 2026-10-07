/**
 * Every component that renders a setting's text, found in the source tree.
 *
 * The narrow-width test used to hold a hand-picked list of surfaces, and a
 * surface nobody listed (the readonly branch of `TweakSetting`, the Home
 * advisory cards) shipped overflowing its frame. A component belongs here when
 * its source imports from `types/setting`: that import is what it takes to
 * render a setting's fields. A new component that renders settings is therefore
 * found without anyone editing a list, and the test either renders it or
 * demands an explicit, reasoned exclusion.
 */

import { createElement, type ComponentType } from "react";
import type { HardwareInfo } from "../lib/api";
import type { Setting } from "../types/setting";
import { makeRunner } from "./runner";

const SOURCES = import.meta.glob(["../components/**/*.tsx", "!../components/**/__tests__/**"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const MODULES = import.meta.glob(["../components/**/*.tsx", "!../components/**/__tests__/**"], {
  eager: true,
}) as Record<string, Record<string, unknown>>;

const IMPORTS_SETTING = /from\s+"\.\.\/(?:\.\.\/)?types\/setting"/;

export interface DiscoveredSurface {
  /** `components/ActionRow.tsx#ActionRow`: unique and stable. */
  id: string;
  /** The exported component's name. */
  name: string;
  Component: ComponentType<Record<string, unknown>>;
}

const Icon = () => createElement("svg", { "aria-hidden": true });

/** A machine whose every device carries the one long text as its name. */
function machineNamed(long: string): HardwareInfo {
  return {
    cpu: { name: long, physical_cores: 8, logical_cores: 16, architecture: "x64" },
    gpus: [{ vendor: "NVIDIA", name: long }],
    monitors: [
      { name: long, friendly_name: long, width: 2560, height: 1440, is_primary: true, setting_key: "narrow" },
    ],
    network_adapters: [
      {
        name: long,
        description: long,
        adapter_type: "Ethernet",
        status: "Up",
        is_enabled: true,
        is_connected: true,
        dns_servers: [],
        interface_index: 1,
        setting_key: "narrow",
      },
    ],
    storage_drives: [
      { drive_letter: "C", model: long, media_type: "SSD", size_gb: 1000, trim_enabled: true },
    ],
    audio_devices: [],
    detecting: false,
  };
}

/**
 * Every prop name any surface takes, filled with one text. A component reads
 * the ones it declares and ignores the rest; one that needs a prop this bag does
 * not carry fails to render, and the test that renders it must name it.
 */
export function genericProps(settings: Setting[], long: string): Record<string, unknown> {
  return {
    hardware: machineNamed(long),
    renderRows: () => null,
    setting: settings[0],
    settings,
    rows: settings.map((setting) => ({ setting })),
    runner: makeRunner(),
    name: long,
    title: long,
    subtitle: long,
    summary: long,
    kind: long,
    deviceKey: "narrow-probe",
    icon: Icon,
    accent: "software",
    detecting: false,
    categoryLabel: () => long,
    initialCollapsed: false,
    match: () => true,
    categoriesWithSettings: [
      {
        category: {
          id: "network",
          displayName: long,
          description: long,
          icon: "Wifi",
          color: "text-blue-500",
          isActionOnly: false,
          order: 1,
        },
        settings,
      },
    ],
    moduleMetaMap: new Map(),
    definitionsLoading: false,
    gpuCategoryStatus: "success",
    hasGpuSettings: false,
    getIconByName: () => Icon,
  };
}

export function discoverSurfaces(): DiscoveredSurface[] {
  const found: DiscoveredSurface[] = [];
  for (const [path, source] of Object.entries(SOURCES)) {
    if (!IMPORTS_SETTING.test(source)) continue;
    const exports = MODULES[path] ?? {};
    for (const [name, value] of Object.entries(exports)) {
      if (!/^[A-Z]/.test(name) || typeof value !== "function") continue;
      found.push({
        id: `${path.replace("../", "")}#${name}`,
        name,
        Component: value as ComponentType<Record<string, unknown>>,
      });
    }
  }
  return found.sort((a, b) => a.id.localeCompare(b.id));
}
