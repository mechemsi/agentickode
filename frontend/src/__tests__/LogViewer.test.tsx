// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import LogViewer from "../components/runs/LogViewer";

vi.mock("../api", () => ({
  getRunLogs: vi.fn().mockResolvedValue([]),
}));

import { getRunLogs } from "../api";
const mockGetRunLogs = vi.mocked(getRunLogs);

// Mock WebSocket
class MockWebSocket {
  onmessage: ((ev: { data: string }) => void) | null = null;
  close = vi.fn();
  url: string;

  constructor(url: string) {
    this.url = url;
    // Default: send a coding log after a tick
    setTimeout(() => {
      this.onmessage?.({
        data: JSON.stringify({
          id: 100,
          timestamp: "2024-01-01T00:00:00Z",
          phase: "coding",
          level: "info",
          message: "Test log message",
        }),
      });
    }, 10);
  }
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", MockWebSocket);
  mockGetRunLogs.mockReset().mockResolvedValue([]);
});

describe("LogViewer", () => {
  it("shows waiting message initially when no phase filter", () => {
    render(<LogViewer runId={1} />);
    expect(screen.getByText("Waiting for logs...")).toBeInTheDocument();
  });

  it("renders received log messages", async () => {
    render(<LogViewer runId={1} />);
    const msg = await screen.findByText("Test log message", {}, { timeout: 1000 });
    expect(msg).toBeInTheDocument();
  });

  it("fetches historical logs when phase is set", async () => {
    mockGetRunLogs.mockResolvedValue([
      { id: 1, run_id: 1, timestamp: "2024-01-01T00:00:00Z", phase: "planning", level: "info", message: "Historical log" },
    ]);
    render(<LogViewer runId={1} phase="planning" />);
    await waitFor(() => {
      expect(mockGetRunLogs).toHaveBeenCalledWith(1, { phase: "planning" });
    });
    expect(await screen.findByText("Historical log")).toBeInTheDocument();
  });

  it("filters WebSocket messages by phase", async () => {
    // WS sends a "coding" message, but we're filtering for "planning"
    render(<LogViewer runId={1} phase="planning" />);
    // The WS message for "coding" should be filtered out
    // Wait a bit for the WS message to arrive
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText("Test log message")).not.toBeInTheDocument();
  });

  it("shows phase-specific empty state", () => {
    render(<LogViewer runId={1} phase="planning" />);
    expect(screen.getByText("No logs for planning")).toBeInTheDocument();
  });

  it("renders metadata toggle for logs with metadata_", async () => {
    mockGetRunLogs.mockResolvedValue([
      {
        id: 1,
        run_id: 1,
        timestamp: "2024-01-01T00:00:00Z",
        phase: "planning",
        level: "info",
        message: "System prompt",
        metadata_: { category: "system_prompt", system_prompt_text: "You are an architect" },
      },
    ]);
    render(<LogViewer runId={1} phase="planning" />);
    const toggle = await screen.findByTestId("metadata-toggle");
    expect(toggle).toBeInTheDocument();
    expect(screen.getByText("System Prompt")).toBeInTheDocument();
  });
});