// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AgentInvocation } from "../types";

// vi.mock is hoisted — do not reference variables defined in the test file here
vi.mock("../api", () => ({
  getRunInvocations: vi.fn(),
}));

import { getRunInvocations } from "../api";
import AgentActivityPanel from "../components/runs/AgentActivityPanel";

const mockInvocations: AgentInvocation[] = [
  {
    id: 1,
    run_id: 42,
    phase_execution_id: null,
    workspace_server_id: null,
    agent_name: "claude",
    phase_name: "coding",
    subtask_index: 0,
    subtask_title: "Implement feature",
    prompt_chars: 250,
    response_chars: 1500,
    exit_code: 0,
    files_changed: ["src/api.ts", "src/types.ts"],
    duration_seconds: 87.4,
    status: "success",
    error_message: null,
    started_at: "2024-01-01T10:00:00Z",
    completed_at: "2024-01-01T10:01:27Z",
    estimated_tokens_in: null,
    estimated_tokens_out: null,
    estimated_cost_usd: null,
    session_id: null,
    metadata_: { command: "claude --no-stream" },
  },
  {
    id: 2,
    run_id: 42,
    phase_execution_id: null,
    workspace_server_id: null,
    agent_name: "ollama/qwen2.5",
    phase_name: "reviewing",
    subtask_index: 0,
    subtask_title: "Review attempt 1",
    prompt_chars: 800,
    response_chars: 400,
    exit_code: null,
    files_changed: null,
    duration_seconds: 23.1,
    status: "success",
    error_message: null,
    started_at: "2024-01-01T10:02:00Z",
    completed_at: "2024-01-01T10:02:23Z",
    estimated_tokens_in: null,
    estimated_tokens_out: null,
    estimated_cost_usd: null,
    session_id: null,
    metadata_: null,
  },
];

describe("AgentActivityPanel", () => {
  beforeEach(() => {
    (getRunInvocations as ReturnType<typeof vi.fn>).mockResolvedValue(mockInvocations);
  });

  it("renders the panel heading", async () => {
    render(<AgentActivityPanel runId={42} />);
    expect(await screen.findByText("Agent Activity")).toBeInTheDocument();
  });

  it("shows invocation count", async () => {
    render(<AgentActivityPanel runId={42} />);
    expect(await screen.findByText("2 invocation(s)")).toBeInTheDocument();
  });

  it("displays agent names", async () => {
    render(<AgentActivityPanel runId={42} />);
    expect(await screen.findByText("claude")).toBeInTheDocument();
    expect(await screen.findByText("ollama/qwen2.5")).toBeInTheDocument();
  });

  it("displays phase badges", async () => {
    render(<AgentActivityPanel runId={42} />);
    expect(await screen.findByText("coding")).toBeInTheDocument();
    expect(await screen.findByText("reviewing")).toBeInTheDocument();
  });

  it("displays status for each invocation", async () => {
    render(<AgentActivityPanel runId={42} />);
    const successBadges = await screen.findAllByText("success");
    expect(successBadges.length).toBeGreaterThanOrEqual(2);
  });

  it("shows subtask title with index", async () => {
    render(<AgentActivityPanel runId={42} />);
    expect(await screen.findByText("[1] Implement feature")).toBeInTheDocument();
  });

  it("shows empty state when no invocations", async () => {
    (getRunInvocations as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);

    render(<AgentActivityPanel runId={99} />);
    expect(
      await screen.findByText("No agent invocations recorded yet."),
    ).toBeInTheDocument();
  });

  it("renders without crashing when invocations have null fields", async () => {
    const nullInvocation: AgentInvocation = {
      id: 3,
      run_id: 42,
      phase_execution_id: null,
      workspace_server_id: null,
      agent_name: "claude",
      phase_name: null,
      subtask_index: null,
      subtask_title: null,
      prompt_chars: 0,
      response_chars: 0,
      exit_code: null,
      files_changed: null,
      duration_seconds: null,
      status: "running",
      error_message: null,
      started_at: null,
      completed_at: null,
      estimated_tokens_in: null,
      estimated_tokens_out: null,
      estimated_cost_usd: null,
      session_id: null,
      metadata_: null,
    };
    (getRunInvocations as ReturnType<typeof vi.fn>).mockResolvedValueOnce([nullInvocation]);

    render(<AgentActivityPanel runId={42} />);
    expect(await screen.findByText("running")).toBeInTheDocument();
  });
});