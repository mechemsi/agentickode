// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getRun: vi.fn().mockResolvedValue({
    id: 1, task_id: "TASK-1", project_id: "proj-1", title: "Fix bug",
    description: "desc", branch_name: "feature/ai-TASK-1", status: "running",
    current_phase: "coding", retry_count: 0, max_retries: 3,
    error_message: null, pr_url: null, approved: null, rejection_reason: null,
    created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z",
    started_at: null, completed_at: null, run_type: "ai_task",
    workspace_path: "/ws", repo_owner: "org", repo_name: "repo",
    default_branch: "main", task_source: "plane", git_provider: "gitea",
    task_source_meta: {}, use_claude_api: false, workspace_config: null,
    workspace_result: null, planning_result: null, coding_results: null,
    test_results: null, review_result: null, approval_requested_at: null,
    phase_started_at: null, phase_executions: [],
    workflow_template_id: null, parent_run_id: null,
  }),
  getWorkflowTemplate: vi.fn().mockResolvedValue({ id: 5, name: "pr-review" }),
  getRunInvocations: vi.fn().mockResolvedValue([]),
  retryRun: vi.fn(),
  restartRun: vi.fn(),
  cancelRun: vi.fn(),
  advancePhase: vi.fn(),
}));

import RunDetail from "../pages/RunDetail";

describe("RunDetail", () => {
  it("renders the run title", async () => {
    render(
      <MemoryRouter initialEntries={["/runs/1"]}>
        <Routes>
          <Route path="/runs/:id" element={<RunDetail />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("Fix bug")).toBeInTheDocument();
  });

  it("shows cancel button for running status", async () => {
    render(
      <MemoryRouter initialEntries={["/runs/1"]}>
        <Routes>
          <Route path="/runs/:id" element={<RunDetail />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("Cancel")).toBeInTheDocument();
  });

  it("shows workflow template name when workflow_template_id is present", async () => {
    const { getRun, getWorkflowTemplate } = await import("../api");
    (getRun as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 1, task_id: "TASK-1", project_id: "proj-1", title: "Fix bug",
      description: "desc", branch_name: "feature/ai-TASK-1", status: "running",
      current_phase: "coding", retry_count: 0, max_retries: 3,
      error_message: null, pr_url: null, approved: null, rejection_reason: null,
      created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z",
      started_at: null, completed_at: null, run_type: "ai_task",
      workspace_path: "/ws", repo_owner: "org", repo_name: "repo",
      default_branch: "main", task_source: "plane", git_provider: "gitea",
      task_source_meta: {}, use_claude_api: false, workspace_config: null,
      workspace_result: null, planning_result: null, coding_results: null,
      test_results: null, review_result: null, approval_requested_at: null,
      phase_started_at: null, phase_executions: [],
      workflow_template_id: 5, parent_run_id: null,
    });
    (getWorkflowTemplate as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 5,
      name: "pr-review",
    });

    render(
      <MemoryRouter initialEntries={["/runs/1"]}>
        <Routes>
          <Route path="/runs/:id" element={<RunDetail />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("pr-review")).toBeInTheDocument();
  });
});