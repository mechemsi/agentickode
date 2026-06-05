// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import StepEditor from "../components/workflows/StepEditor";
import type { PhaseConfig } from "../types";

const baseStep: PhaseConfig = {
  phase_name: "my-step",
  kind: "bash",
  enabled: true,
  trigger_mode: "auto",
  notify_source: false,
  timeout_seconds: null,
  params: { command: "echo hi" },
};

function renderEditor(step: Partial<PhaseConfig> = {}, onChange = vi.fn()) {
  const props = {
    step: { ...baseStep, ...step } as PhaseConfig,
    onChange,
    onRemove: vi.fn(),
    onMoveUp: vi.fn(),
    onMoveDown: vi.fn(),
    canMoveUp: true,
    canMoveDown: true,
    legacyPhaseNames: ["workspace_setup", "init", "coding"],
  };
  render(<StepEditor {...props} />);
  return { onChange, onRemove: props.onRemove };
}

describe("StepEditor", () => {
  it("renders the bash command textarea for a bash step", () => {
    renderEditor({ kind: "bash", params: { command: "make build" } });
    const textarea = screen.getByDisplayValue("make build");
    expect(textarea).toBeInTheDocument();
  });

  it("renders the prompt textarea for an agent step", () => {
    renderEditor({ kind: "agent", params: { prompt: "Fix {{run.title}}" } });
    expect(screen.getByDisplayValue("Fix {{run.title}}")).toBeInTheDocument();
  });

  it("renders the legacy phase dropdown for a legacy_phase step", () => {
    renderEditor({ kind: "legacy_phase", phase_name: "coding" });
    // Phase-name input + the legacy dropdown will both show the value
    const matches = screen.getAllByDisplayValue("coding");
    expect(matches.length).toBeGreaterThan(0);
  });

  it("calls onChange with the new kind when kind dropdown changes", () => {
    const { onChange } = renderEditor({ kind: "bash", params: { command: "x" } });
    const selects = screen.getAllByRole("combobox");
    // The first combobox is the kind selector (per StepEditor layout)
    fireEvent.change(selects[0], { target: { value: "agent" } });
    expect(onChange).toHaveBeenCalled();
    const calls = onChange.mock.calls;
    const lastCall = calls[calls.length - 1]?.[0];
    expect(lastCall.kind).toBe("agent");
  });

  it("calls onRemove when the ✕ button is clicked", () => {
    const { onRemove } = renderEditor();
    const removeBtn = screen.getByRole("button", { name: /remove step/i });
    fireEvent.click(removeBtn);
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
