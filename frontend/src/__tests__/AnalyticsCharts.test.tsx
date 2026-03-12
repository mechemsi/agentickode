// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import AnalyticsCharts from "../components/shared/AnalyticsCharts";

const baseData = {
  success_rate: 75.0,
  avg_duration_seconds: 90,
  total_runs: 10,
  runs_by_status: { completed: 8, failed: 2 },
  avg_phase_durations: [],
  agent_stats: [],
  runs_over_time: [],
};

describe("AnalyticsCharts", () => {
  it("renders nothing when data is null", () => {
    const { container } = render(<AnalyticsCharts data={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders success rate card", () => {
    render(<AnalyticsCharts data={baseData} />);
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("1m 30s")).toBeInTheDocument();
  });

  it("renders cost metric card with cost_stats", () => {
    render(
      <AnalyticsCharts
        data={{
          ...baseData,
          cost_stats: {
            total_cost_usd: 1.2345,
            total_tokens_in: 5000,
            total_tokens_out: 10000,
            avg_cost_per_run_usd: 0.1235,
            cost_by_agent: [{ agent_name: "claude", cost_usd: 1.2345 }],
          },
        }}
      />,
    );
    expect(screen.getByText("$1.23")).toBeInTheDocument();
    expect(screen.getByText("Est. Total Cost")).toBeInTheDocument();
  });

  it("renders N/A when cost_stats is missing", () => {
    render(<AnalyticsCharts data={baseData} />);
    expect(screen.getByText("N/A")).toBeInTheDocument();
    expect(screen.getByText("Est. Total Cost")).toBeInTheDocument();
  });
});