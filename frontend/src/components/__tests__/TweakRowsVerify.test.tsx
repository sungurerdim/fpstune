/**
 * Verify is a detect: there is no verify endpoint to ask.
 *
 * The row's Verify button used to post `/settings/{id}/verify`, a route that
 * answered a second, narrower question than detect. It now re-reads the setting
 * through the one path every detection takes into the store.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { TweakRows } from "../TweakRows";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const redetectSettings = vi.fn().mockResolvedValue(undefined);

vi.mock("../../lib/detection-manager", () => ({
  detectionManager: {
    redetectSettings: (ids: string[]) => redetectSettings(ids),
  },
}));

vi.mock("../TweakSetting", () => ({
  TweakSetting: ({
    setting,
    onVerify,
  }: {
    setting: Setting;
    onVerify: () => void;
  }) => (
    <button type="button" onClick={onVerify}>
      verify {setting.id}
    </button>
  ),
}));

const NAGLE = {
  id: "network:nagle",
  displayName: "Nagle's Algorithm",
} as unknown as Setting;

describe("a row's Verify re-detects the setting", () => {
  beforeEach(() => {
    redetectSettings.mockClear();
    useStore.setState({
      settings: new Map(),
      selectedSettingIds: new Set(),
      operationStatus: {},
    } as never);
  });

  it("asks the detection manager for that one setting and nothing else", async () => {
    const user = userEvent.setup();
    render(<TweakRows rows={[{ setting: NAGLE }]} />);

    await user.click(screen.getByRole("button", { name: "verify network:nagle" }));

    expect(redetectSettings).toHaveBeenCalledTimes(1);
    expect(redetectSettings).toHaveBeenCalledWith(["network:nagle"]);
  });
});
