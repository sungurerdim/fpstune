import {
  Clock,
  Cpu,
  FileCode,
  Gamepad2,
  HardDrive,
  MonitorPlay,
  Palette,
  Settings,
  Volume2,
  Wifi,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";

/**
 * Every icon the backend's category metadata names, imported one by one.
 *
 * The lookup used to index `import * as LucideIcons`, which kept all of
 * lucide-react in the bundle: 635 KB of a 1.3 MB script for a dozen icons.
 * tests/test_settings/test_category_icons.py fails when the backend names an
 * icon that is missing here, so a new category cannot fall back silently.
 */
export const CATEGORY_ICONS: Readonly<Record<string, LucideIcon>> = {
  Clock,
  Cpu,
  FileCode,
  Gamepad2,
  HardDrive,
  MonitorPlay,
  Palette,
  Settings,
  Volume2,
  Wifi,
  Wrench,
  Zap,
};

/** The icon a category names, or the Settings icon for a name not listed. */
export function getIconByName(name: string): LucideIcon {
  return CATEGORY_ICONS[name] ?? Settings;
}
