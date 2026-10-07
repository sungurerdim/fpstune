/**
 * A placeholder is not a label.
 *
 * The tweak lists' search boxes were named by their `placeholder` alone, which
 * several screen readers drop entirely and which disappears from the accessible
 * name the moment the user types. They were also `type="text"`, which is the
 * wrong element for a filter box: it loses the clear affordance and the search
 * semantics for free.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import { OptimizeTab } from "../OptimizeTab";
import { useStore } from "../../store";

vi.mock("../hardware/useHardware", () => ({
  useHardware: () => ({ hardware: null, isLoading: false }),
}));
vi.mock("../hardware/useRefreshOnFocus", () => ({ useRefreshOnFocus: () => undefined }));

describe("the Optimize tab's search box says what it searches", () => {
  beforeEach(() => {
    useStore.setState({
      settings: new Map(),
      selectedSettingIds: new Set(),
      operationStatus: {},
      categoryDetectionStatus: {},
    } as never);
  });

  it("names the search after the same words it shows", () => {
    render(<OptimizeTab />);

    const search = screen.getByRole("searchbox", { name: "Search settings" });
    expect(search).toHaveAttribute("placeholder", "Search settings...");
  });
});
