/**
 * The shared scope header keeps its three levels apart.
 *
 * Each test names the run-together it forbids: a model name, its kind and its
 * counts read as one sentence ("NVIDIA GeForce RTX 3070 Laptop GPU Ekran Kartı
 * Uygulanacak 9 1 senden işlem bekliyor"), a count with no label, actions drawn
 * somewhere other than the title row's right edge.
 */

import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { Metric, MetricList, ScopeHeader } from "../ScopeHeader";

describe("ScopeHeader", () => {
  it("makes the title a real heading at the level asked for, and nothing else in it", () => {
    render(
      <ScopeHeader
        level={3}
        title="NVIDIA GeForce RTX 3070 Laptop GPU"
        kind="Graphics card"
        metrics={
          <MetricList>
            <Metric value={9} label="to apply" />
          </MetricList>
        }
      />,
    );

    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading).toHaveTextContent(/^NVIDIA GeForce RTX 3070 Laptop GPU$/);
  });

  it("puts the kind on its own line under the title, outside the heading", () => {
    render(<ScopeHeader title="Example GPU" kind="Graphics card" />);

    const kind = screen.getByText("Graphics card");
    expect(kind.tagName).toBe("P");
    expect(kind).toHaveAttribute("data-slot", "scope-kind");
    expect(screen.getByRole("heading")).not.toContainElement(kind);
    // Directly after the title, so it reads as its label, not a sibling in a stream.
    expect(screen.getByRole("heading").nextElementSibling).toBe(kind);
  });

  it("sets each count in its own labelled chip inside a list, number apart from its words", () => {
    render(
      <ScopeHeader
        title="Example GPU"
        metrics={
          <MetricList label="Status">
            <Metric tone="attention" value={9} label="to apply" />
            <Metric tone="advisory" value={1} label="need you" />
          </MetricList>
        }
      />,
    );

    const list = screen.getByRole("list", { name: "Status" });
    const chips = within(list).getAllByRole("listitem");
    expect(chips.map((c) => c.textContent)).toEqual(["9 to apply", "1 need you"]);
    // The number is its own bold element, so the eye can find it without reading.
    expect(within(chips[0]).getByText("9")).toHaveClass("font-bold");
    expect(within(chips[0]).getByText("to apply")).not.toHaveClass("font-bold");
  });

  it("draws a state with no number as a bare chip", () => {
    render(
      <ScopeHeader
        title="Example SSD"
        metrics={
          <MetricList>
            <Metric tone="ok" label="Ideal" />
          </MetricList>
        }
      />,
    );

    expect(screen.getByRole("listitem")).toHaveTextContent(/^Ideal$/);
  });

  it("puts the actions in the title row, ahead of the metrics row", () => {
    render(
      <ScopeHeader
        title="Example GPU"
        actions={<button type="button">Apply</button>}
        metrics={
          <MetricList>
            <Metric value={1} label="to apply" />
          </MetricList>
        }
      />,
    );

    const header = screen.getByRole("heading").closest("[data-slot='scope-header']") as HTMLElement;
    const actions = header.querySelector("[data-slot='scope-actions']") as HTMLElement;
    const metrics = header.querySelector("[data-slot='scope-metrics']") as HTMLElement;
    expect(within(actions).getByRole("button", { name: "Apply" })).toBeInTheDocument();
    // Actions precede the metrics row in the document, so they stay on the title row.
    expect(actions.compareDocumentPosition(metrics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("gives the heading the id it is handed, so a section can be labelled by it", () => {
    render(<ScopeHeader title="Network" headingId="net-title" />);

    expect(screen.getByRole("heading", { name: "Network" })).toHaveAttribute("id", "net-title");
  });
});
