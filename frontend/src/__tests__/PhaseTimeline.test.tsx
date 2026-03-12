// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import PhaseTimeline from "../components/runs/PhaseTimeline";
import type { PhaseExecution } from "../types";

function makePhase(overrides: Partial<PhaseExecution> & { phase_name: string; order_index: number }): PhaseExecution {
  return {
    id: overrides.order_index + 1,
    run_id: 1,
    trigger_mode: "auto",
    status: "pending",
    result: null,
    error_message: null,
    retry_count: 0,
    max_retries: 3,
    agent_override: null,
    notify_source: false,
    phase_config: null,
    started_at: null,
    completed_at: null,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("PhaseTimeline", () => {
  // Fallback mode tests
  it("renders all phase labels in fallback mode", () => {
    render(<PhaseTimeline currentPhase={null} status="pending" />);
    expect(screen.getByText("Workspace Setup")).toBeInTheDocument();
    expect(screen.getByText("Planning")).toBeInTheDocument();
    expect(screen.getByText("Finalization")).toBeInTheDocument();
  });

  it("highlights current phase in blue (fallback)", () => {
    const { container } = render(<PhaseTimeline currentPhase="coding" status="running" />);
    const spans = container.querySelectorAll("span");
    const codingSpan = Array.from(spans).find(s => s.textContent === "Coding");
    expect(codingSpan).toHaveClass("text-blue-300");
  });

  it("marks completed phases in green when status=completed (fallback)", () => {
    const { container } = render(<PhaseTimeline currentPhase="finalization" status="completed" />);
    const spans = container.querySelectorAll("span");
    const setupSpan = Array.from(spans).find(s => s.textContent === "Workspace Setup");
    expect(setupSpan).toHaveClass("text-green-300");
  });

  // PhaseExecution mode tests
  it("renders phases from PhaseExecution data", () => {
    const phases = [
      makePhase({ phase_name: "workspace_setup", order_index: 0, status: "completed" }),
      makePhase({ phase_name: "coding", order_index: 1, status: "running" }),
      makePhase({ phase_name: "reviewing", order_index: 2, status: "pending" }),
    ];
    render(<PhaseTimeline phases={phases} />);
    expect(screen.getByText("Workspace Setup")).toBeInTheDocument();
    expect(screen.getByText("Coding")).toBeInTheDocument();
    expect(screen.getByText("Reviewing")).toBeInTheDocument();
  });

  it("shows retry count when > 0", () => {
    const phases = [
      makePhase({ phase_name: "coding", order_index: 0, status: "running", retry_count: 2 }),
    ];
    render(<PhaseTimeline phases={phases} />);
    expect(screen.getByText("(2x)")).toBeInTheDocument();
  });

  it("shows Advance button for wait_for_trigger phases", () => {
    const onAdvance = vi.fn();
    const phases = [
      makePhase({ phase_name: "coding", order_index: 0, status: "waiting", trigger_mode: "wait_for_trigger" }),
    ];
    render(<PhaseTimeline phases={phases} onAdvance={onAdvance} />);
    const btn = screen.getByText("Advance");
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onAdvance).toHaveBeenCalledWith("coding");
  });

  it("shows Awaiting Approval badge for wait_for_approval phases", () => {
    const phases = [
      makePhase({ phase_name: "approval", order_index: 0, status: "waiting", trigger_mode: "wait_for_approval" }),
    ];
    render(<PhaseTimeline phases={phases} />);
    expect(screen.getByText("Awaiting Approval")).toBeInTheDocument();
  });

  it("does not show Advance button without onAdvance callback", () => {
    const phases = [
      makePhase({ phase_name: "coding", order_index: 0, status: "waiting", trigger_mode: "wait_for_trigger" }),
    ];
    render(<PhaseTimeline phases={phases} />);
    expect(screen.queryByText("Advance")).not.toBeInTheDocument();
  });

  // Click-to-filter tests
  it("calls onPhaseClick when a phase is clicked", () => {
    const onPhaseClick = vi.fn();
    const phases = [
      makePhase({ phase_name: "planning", order_index: 0, status: "completed" }),
      makePhase({ phase_name: "coding", order_index: 1, status: "running" }),
    ];
    render(<PhaseTimeline phases={phases} onPhaseClick={onPhaseClick} />);
    fireEvent.click(screen.getByText("Planning"));
    expect(onPhaseClick).toHaveBeenCalledWith("planning");
  });

  it("highlights selected phase with ring", () => {
    const phases = [
      makePhase({ phase_name: "planning", order_index: 0, status: "completed" }),
      makePhase({ phase_name: "coding", order_index: 1, status: "running" }),
    ];
    render(
      <PhaseTimeline phases={phases} selectedPhase="planning" onPhaseClick={vi.fn()} />,
    );
    const planningSpan = screen.getByText("Planning").closest("span[role='button']");
    expect(planningSpan).toHaveClass("ring-2");
    expect(planningSpan).toHaveClass("ring-blue-400");
  });

  it("shows 'All Logs' chip and calls onPhaseClick(null) when clicked", () => {
    const onPhaseClick = vi.fn();
    const phases = [
      makePhase({ phase_name: "coding", order_index: 0, status: "running" }),
    ];
    render(<PhaseTimeline phases={phases} selectedPhase="coding" onPhaseClick={onPhaseClick} />);
    const allLogsBtn = screen.getByText("All Logs");
    expect(allLogsBtn).toBeInTheDocument();
    fireEvent.click(allLogsBtn);
    expect(onPhaseClick).toHaveBeenCalledWith(null);
  });

  it("highlights 'All Logs' when no phase is selected", () => {
    const phases = [
      makePhase({ phase_name: "coding", order_index: 0, status: "running" }),
    ];
    render(
      <PhaseTimeline phases={phases} selectedPhase={null} onPhaseClick={vi.fn()} />,
    );
    const allLogsBtn = screen.getByText("All Logs");
    expect(allLogsBtn).toHaveClass("ring-2");
    expect(allLogsBtn).toHaveClass("ring-blue-400");
  });

  it("shows duration for completed phases", () => {
    const phases = [
      makePhase({
        phase_name: "planning",
        order_index: 0,
        status: "completed",
        started_at: "2024-01-01T00:00:00Z",
        completed_at: "2024-01-01T00:00:45Z",
      }),
    ];
    render(<PhaseTimeline phases={phases} />);
    expect(screen.getByText((_, el) => el?.textContent === "(45s)")).toBeInTheDocument();
  });
});