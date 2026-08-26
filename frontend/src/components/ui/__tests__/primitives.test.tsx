/**
 * The E2 primitives keep their contracts.
 *
 * Each test names the drift it forbids: a busy button that stays clickable
 * (the bug thirteen hand-rolled buttons each solved differently), a meter
 * with no accessible value (a bar a screen reader reads as decoration), an
 * alert that does not announce, a progress value escaping 0..100.
 */

import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Button } from "../Button";
import { Card, CardHeader } from "../Card";
import { Badge } from "../Badge";
import { Alert, EmptyState, Meter, Progress, Skeleton } from "../Feedback";

describe("Button", () => {
  it("busy means not clickable, announced busy", () => {
    const onClick = vi.fn();
    render(
      <Button busy onClick={onClick}>
        Apply
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Apply" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("defaults to type=button so it cannot submit a form by accident", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });
});

describe("Card", () => {
  it("the header title is a real heading, count beside it", () => {
    render(
      <Card>
        <CardHeader title="Hardware tweaks" count={4} />
      </Card>,
    );
    expect(
      screen.getByRole("heading", { name: "Hardware tweaks" }),
    ).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
});

describe("Badge", () => {
  it("renders its label", () => {
    render(<Badge tone="warning">advanced</Badge>);
    expect(screen.getByText("advanced")).toBeInTheDocument();
  });
});

describe("Progress", () => {
  it("carries an accessible name and a clamped value", () => {
    render(<Progress value={140} label="Scan progress" />);
    const bar = screen.getByRole("progressbar", { name: "Scan progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "100");
  });
});

describe("Meter", () => {
  it("is a meter with real bounds, not a decorated div", () => {
    render(<Meter value={57} max={297} label="Frames vs display target" />);
    const meter = screen.getByRole("meter", {
      name: "Frames vs display target",
    });
    expect(meter).toHaveAttribute("aria-valuenow", "57");
    expect(meter).toHaveAttribute("aria-valuemax", "297");
  });
});

describe("Alert", () => {
  it("warnings announce; info does not interrupt", () => {
    render(
      <>
        <Alert tone="warning" title="This may reboot" />
        <Alert tone="info" title="Nothing has been changed yet" />
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("This may reboot");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Nothing has been changed yet",
    );
  });
});

describe("EmptyState / Skeleton", () => {
  it("empty says why; skeleton is invisible to readers", () => {
    const { container } = render(
      <>
        <EmptyState title="Nothing to reclaim right now." />
        <Skeleton className="h-4 w-24" />
      </>,
    );
    expect(
      screen.getByText("Nothing to reclaim right now."),
    ).toBeInTheDocument();
    expect(
      container.querySelector('[aria-hidden="true"].animate-pulse'),
    ).not.toBeNull();
  });
});
