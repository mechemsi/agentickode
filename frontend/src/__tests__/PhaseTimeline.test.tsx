// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PhaseTimeline from "../components/runs/PhaseTimeline";

describe("PhaseTimeline", () => {
  // ADR-009: a run is a single agent call, so PhaseTimeline just surfaces the
  // current step (or a terminal status placeholder).
  it("renders Pending placeholder when no currentPhase and not completed", () => {
    render(<PhaseTimeline currentPhase={null} status="pending" />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders Completed placeholder when no currentPhase and completed", () => {
    render(<PhaseTimeline currentPhase={null} status="completed" />);
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("highlights current phase in blue", () => {
    const { container } = render(<PhaseTimeline currentPhase="agent" status="running" />);
    const spans = container.querySelectorAll("span");
    const agentSpan = Array.from(spans).find((s) => s.textContent === "Agent");
    expect(agentSpan).toHaveClass("text-blue-300");
  });

  it("marks current phase green when status=completed", () => {
    const { container } = render(
      <PhaseTimeline currentPhase="finalization" status="completed" />,
    );
    const spans = container.querySelectorAll("span");
    const finalSpan = Array.from(spans).find((s) => s.textContent === "Finalization");
    expect(finalSpan).toHaveClass("text-green-300");
  });
});
