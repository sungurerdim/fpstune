import { memo, useState, useCallback } from "react";
import { useStore, type OperationStatus } from "../store";
import { useApplySingle } from "../hooks/useApplySingle";
import { detectionManager } from "../lib/detection-manager";
import type { Setting } from "../types/setting";
import { TweakSetting } from "./TweakSetting";

/** A setting plus where it came from, resolved once so the row does not look it up. */
export interface TweakRow {
  setting: Setting;
  /** e.g. "Network · Adapters". Omitted where the section heading already says it. */
  contextLabel?: string;
  contextIcon?: React.ReactNode;
}

interface TweakRowItemProps extends TweakRow {
  isPending: boolean;
  isSelected: boolean;
  operationStatus?: OperationStatus;
  applySingle: (setting: Setting, value: unknown) => void;
  undoSingle: (setting: Setting) => void;
  verify: (setting: Setting) => void;
  toggleSelectedSetting: (id: Setting["id"]) => void;
}

/**
 * One row, holding the four closures it needs rather than being handed them.
 *
 * The list re-renders on every `_settingsVersion` bump — once per category
 * during a scan, once per apply — and the bump replaces only the settings that
 * actually changed. Building `onApplyValue`, `onReset`, `onUndo`, `onVerify`
 * and `onSelect` in the parent handed all eighty rows five new props each time,
 * which is exactly the comparison a memo would fail on. Built here, they are
 * recreated only when this row's own props move.
 */
const TweakRowItem = memo(
  function TweakRowItem({
    setting,
    contextLabel,
    contextIcon,
    isPending,
    isSelected,
    operationStatus,
    applySingle,
    undoSingle,
    verify,
    toggleSelectedSetting,
  }: TweakRowItemProps) {
    return (
      <TweakSetting
        setting={setting}
        isPending={isPending}
        isModuleLoading={false}
        onApplyValue={(value) => applySingle(setting, value)}
        onReset={() => applySingle(setting, setting.defaultValue)}
        onUndo={() => undoSingle(setting)}
        onVerify={() => verify(setting)}
        isSelected={isSelected}
        onSelect={() => toggleSelectedSetting(setting.id)}
        operationStatus={operationStatus}
        contextLabel={contextLabel}
        contextIcon={contextIcon}
      />
    );
  },
  (previous, next) =>
    previous.setting === next.setting &&
    previous.contextLabel === next.contextLabel &&
    previous.isPending === next.isPending &&
    previous.isSelected === next.isSelected &&
    previous.operationStatus === next.operationStatus &&
    previous.applySingle === next.applySingle &&
    previous.undoSingle === next.undoSingle &&
    previous.verify === next.verify &&
    previous.toggleSelectedSetting === next.toggleSelectedSetting,
  // `contextIcon` is deliberately absent from that list. It is a fresh element
  // on every rebuild of the row list, so comparing it would fail every time and
  // the memo would never hold — and it carries no information of its own: the
  // icon is the category's, and `contextLabel` names that category. Same label,
  // same icon.
);

/**
 * The rows themselves — one setting per line, no card and nothing to expand.
 *
 * Lifted out of `SettingsTab` when the Game Tweaks tab needed the same list: apply,
 * reset, undo and verify are one behaviour, and a second copy of it is a second
 * place for undo to fall through to reset.
 */
export function TweakRows({ rows }: { rows: TweakRow[] }) {
  const selectedSettingIds = useStore((state) => state.selectedSettingIds);
  const toggleSelectedSetting = useStore(
    (state) => state.toggleSelectedSetting,
  );
  const operationStatus = useStore((state) => state.operationStatus);
  const { applySingle, undoSingle, isPending } = useApplySingle();
  const [verifyingIds, setVerifyingIds] = useState<Set<string>>(new Set());

  const verify = useCallback(async (setting: Setting) => {
    setVerifyingIds((prev) => new Set(prev).add(setting.id));
    try {
      await detectionManager.redetectSettings([setting.id]);
    } finally {
      setVerifyingIds((prev) => {
        const next = new Set(prev);
        next.delete(setting.id);
        return next;
      });
    }
  }, []);

  return (
    <div className="space-y-0.5">
      {rows.map(({ setting, contextLabel, contextIcon }) => (
        <TweakRowItem
          key={setting.id}
          setting={setting}
          contextLabel={contextLabel}
          contextIcon={contextIcon}
          isPending={isPending(setting.id) || verifyingIds.has(setting.id)}
          isSelected={selectedSettingIds.has(setting.id)}
          operationStatus={operationStatus[setting.id]}
          applySingle={applySingle}
          undoSingle={undoSingle}
          verify={verify}
          toggleSelectedSetting={toggleSelectedSetting}
        />
      ))}
    </div>
  );
}
