/**
 * A placeholder is not a label.
 *
 * Both tweak lists open with the same row: a search box, then a `<select>`. The
 * selects carried `aria-label`; the search boxes were named by their
 * `placeholder` alone, which several screen readers drop entirely and which
 * disappears from the accessible name the moment the user types. Within one row,
 * that inconsistency is what marks it as an oversight rather than a decision.
 *
 * They were also `type="text"`, which is the wrong element for a filter box: it
 * loses the clear affordance and the search semantics for free.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import { Wifi } from "lucide-react";
import { SettingsTab } from "../SettingsTab";
import { GameTweaksTab } from "../GameTweaksTab";
import { useStore } from "../../store";

describe("each tweak list's search box says what it searches", () => {
  beforeEach(() => {
    useStore.setState({
      settings: new Map(),
      selectedSettingIds: new Set(),
      operationStatus: {},
      categoryDetectionStatus: {},
    } as never);
  });

  it("names the Software Tweaks search after the same words it shows", () => {
    render(
      <SettingsTab
        categoriesWithSettings={[]}
        moduleMetaMap={new Map()}
        definitionsLoading={false}
        gpuCategoryStatus="done"
        hasGpuSettings={false}
        getIconByName={() => Wifi}
      />,
    );

    const search = screen.getByRole("searchbox", { name: "Search settings" });
    expect(search).toHaveAttribute("placeholder", "Search settings...");
  });

  it("names the Game Tweaks search after the same words it shows", () => {
    render(<GameTweaksTab />);

    const search = screen.getByRole("searchbox", {
      name: "Search game settings",
    });
    expect(search).toHaveAttribute("placeholder", "Search game settings...");
  });
});
