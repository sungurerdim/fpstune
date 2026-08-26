/**
 * The Docker gate is the one confirmation in this app that guards a destructive
 * act on the user's machine: pruning shuts down Docker Desktop and every WSL
 * distribution to compact their virtual disk. It shipped with no `role`, no
 * `aria-` attribute and no `onKeyDown` at all, so the only way out of it was the
 * mouse. These pin that it is a real dialog and that Escape means "no".
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DockerConfirmModal } from "../DockerConfirmModal";

describe("DockerConfirmModal", () => {
  it("is nothing at all until it is opened", () => {
    render(
      <DockerConfirmModal open={false} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("names itself with the question it is asking", () => {
    render(
      <DockerConfirmModal open onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );

    expect(
      screen.getByRole("dialog", { name: "Restart Docker & WSL?" }),
    ).toHaveAttribute("aria-modal", "true");
  });

  it("dismisses from the keyboard without running the prune", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <DockerConfirmModal open onConfirm={onConfirm} onCancel={onCancel} />,
    );

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("runs the prune only from its own affirmative button", () => {
    const onConfirm = vi.fn();
    render(
      <DockerConfirmModal open onConfirm={onConfirm} onCancel={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Prune & compact" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
