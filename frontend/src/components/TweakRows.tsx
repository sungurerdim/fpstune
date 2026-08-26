import { memo, useState, useCallback } from "react";
import { useStore, type OperationStatus } from "../store";
import { useApplySingle } from "../hooks/useApplySingle";
import { settingsApi } from "../lib/api";
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
  resetSingle: (setting: Setting) => void;
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
    resetSingle,
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
        // The dedicated endpoint, not apply-with-defaultValue: reset is its
        // own promise (C6), and the backend logs and verifies it as one.
        onReset={() => resetSingle(setting)}
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
    previous.resetSingle === next.resetSingle &&
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
  const { applySingle, resetSingle, undoSingle, isPending } = useApplySingle();
  const [verifyingIds, setVerifyingIds] = useState<Set<string>>(new Set());

  const verify = useCallback(async (setting: Setting) => {
    setVerifyingIds((prev) => new Set(prev).add(setting.id));
    try {
      // The dedicated detect-only endpoint: it answers "does the machine
      // match the recommended value?" and names the question in its reply.
      // A bulk re-detect answered the same question by side effect, and left
      // POST /settings/{id}/verify a route nobody called.
      const result = await settingsApi.verifySetting(setting.id);
      if (result.error) {
        // A verify that could not read falls back to the full re-detect
        // path, which also carries applicability and the error text.
        await detectionManager.redetectSettings([setting.id]);
      } else {
        useStore
          .getState()
          .setSettingDetectionResult(
            setting.id,
            result.current_value,
            result.matches,
            true,
          );
      }
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
          resetSingle={resetSingle}
          undoSingle={undoSingle}
          verify={verify}
          toggleSelectedSetting={toggleSelectedSetting}
        />
      ))}
    </div>
  );
}
