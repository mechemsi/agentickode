// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getRuns: vi.fn().mockResolvedValue({
    items: [],
    total: 0,
    offset: 0,
    limit: 50,
  }),
  getStats: vi.fn().mockResolvedValue({
    total_runs: 5, pending: 1, running: 2,
    awaiting_approval: 0, completed: 2, failed: 0,
  }),
  getWorkflowTemplates: vi.fn().mockResolvedValue([]),
  getAnalytics: vi.fn().mockResolvedValue({
    success_rate: 80.0,
    avg_duration_seconds: 120,
    total_runs: 5,
    runs_by_status: { completed: 4, failed: 1 },
    avg_phase_durations: [],
    agent_stats: [],
    runs_over_time: [],
  }),
}));

vi.mock("../api/client", () => ({
  BASE: "/api",
}));

// Mock EventSource for SSE
class MockEventSource {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onmessage: ((ev: any) => void) | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onerror: ((ev: any) => void) | null = null;
  close() {}
}
vi.stubGlobal("EventSource", MockEventSource);

import Dashboard from "../pages/Dashboard";

describe("Dashboard", () => {
  it("renders the heading", async () => {
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("renders the search input", async () => {
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(screen.getByPlaceholderText("Search runs...")).toBeInTheDocument();
  });
});