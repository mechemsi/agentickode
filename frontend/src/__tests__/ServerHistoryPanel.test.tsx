// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockListServerInvocations = vi.fn();

vi.mock("../api", () => ({
  listServerInvocations: (...args: unknown[]) => mockListServerInvocations(...args),
}));

import ServerHistoryPanel from "../components/servers/ServerHistoryPanel";

const sampleInvocation = {
  id: 1,
  run_id: 10,
  phase_execution_id: null,
  workspace_server_id: 1,
  agent_name: "agent/claude@ws-1",
  phase_name: "coding",
  subtask_index: 0,
  subtask_title: "Implement feature X",
  prompt_chars: 500,
  response_chars: 2000,
  exit_code: 0,
  files_changed: ["src/main.py"],
  duration_seconds: 45.2,
  status: "success",
  error_message: null,
  session_id: null,
  started_at: "2026-01-15T10:30:00Z",
  completed_at: "2026-01-15T10:30:45Z",
  metadata_: null,
};

describe("ServerHistoryPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    mockListServerInvocations.mockReturnValue(new Promise(() => {}));
    render(<ServerHistoryPanel serverId={1} />);
    expect(screen.getByText("Loading invocations...")).toBeInTheDocument();
  });

  it("renders invocations when loaded", async () => {
    mockListServerInvocations.mockResolvedValue([sampleInvocation]);
    render(<ServerHistoryPanel serverId={1} />);

    expect(await screen.findByText("agent/claude@ws-1")).toBeInTheDocument();
    expect(screen.getByText("coding")).toBeInTheDocument();
    expect(screen.getByText("Implement feature X")).toBeInTheDocument();
    expect(screen.getByText("45s")).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("#10")).toBeInTheDocument();
  });

  it("shows empty state when no invocations", async () => {
    mockListServerInvocations.mockResolvedValue([]);
    render(<ServerHistoryPanel serverId={1} />);

    expect(await screen.findByText("No invocations found.")).toBeInTheDocument();
  });

  it("shows error on failure", async () => {
    mockListServerInvocations.mockRejectedValue(new Error("Network error"));
    render(<ServerHistoryPanel serverId={1} />);

    expect(await screen.findByText("Failed to load invocations")).toBeInTheDocument();
  });

  it("calls API with correct serverId", async () => {
    mockListServerInvocations.mockResolvedValue([]);
    render(<ServerHistoryPanel serverId={42} />);

    await waitFor(() => {
      expect(mockListServerInvocations).toHaveBeenCalledWith(42, expect.objectContaining({ limit: 20, offset: 0 }));
    });
  });

  it("shows load more button when page is full", async () => {
    const fullPage = Array.from({ length: 20 }, (_, i) => ({
      ...sampleInvocation,
      id: i + 1,
    }));
    mockListServerInvocations.mockResolvedValue(fullPage);
    render(<ServerHistoryPanel serverId={1} />);

    expect(await screen.findByText("Load more")).toBeInTheDocument();
  });

  it("hides load more button when page is not full", async () => {
    mockListServerInvocations.mockResolvedValue([sampleInvocation]);
    render(<ServerHistoryPanel serverId={1} />);

    await screen.findByText("agent/claude@ws-1");
    expect(screen.queryByText("Load more")).not.toBeInTheDocument();
  });

  it("refresh button reloads data", async () => {
    mockListServerInvocations.mockResolvedValue([]);
    render(<ServerHistoryPanel serverId={1} />);

    await screen.findByText("No invocations found.");

    mockListServerInvocations.mockResolvedValue([sampleInvocation]);
    fireEvent.click(screen.getByText("Refresh"));

    expect(await screen.findByText("agent/claude@ws-1")).toBeInTheDocument();
  });
});