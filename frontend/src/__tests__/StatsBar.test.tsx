// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import StatsBar from "../components/shared/StatsBar";
import type { Stats } from "../types";

describe("StatsBar", () => {
  const stats: Stats = {
    total_runs: 10,
    pending: 2,
    running: 1,
    awaiting_approval: 3,
    completed: 3,
    failed: 1,
  };

  it("renders nothing when stats is null", () => {
    const { container } = render(<StatsBar stats={null} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders all stat values", () => {
    render(<StatsBar stats={stats} />);
    expect(screen.getByText("10")).toBeInTheDocument(); // total
    expect(screen.getByText("2")).toBeInTheDocument(); // pending
    expect(screen.getAllByText("1")).toHaveLength(2); // running + failed
    expect(screen.getAllByText("3")).toHaveLength(2); // awaiting + completed
  });

  it("renders all labels", () => {
    render(<StatsBar stats={stats} />);
    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Awaiting")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});