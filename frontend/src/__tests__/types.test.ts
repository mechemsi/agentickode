// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { describe, it, expect } from "vitest";
import type { TaskRun, TaskRunDetail, PhaseExecution, ProjectConfig, Stats } from "../types";

describe("TypeScript interfaces", () => {
  it("TaskRun has required fields", () => {
    const run: TaskRun = {
      id: 1,
      run_type: "ai_task",
      task_id: "TASK-1",
      project_id: "proj-1",
      title: "Test run",
      description: "desc",
      branch_name: "feature/ai-TASK-1",
      status: "pending",
      current_phase: null,
      retry_count: 0,
      error_message: null,
      pr_url: null,
      approved: null,
      rejection_reason: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
      started_at: null,
      completed_at: null,
      parent_run_id: null,
      workflow_template_id: null,
      total_cost_usd: null,
    };
    expect(run.id).toBe(1);
    expect(run.status).toBe("pending");
  });

  it("TaskRunDetail extends TaskRun with phase results", () => {
    const detail: TaskRunDetail = {
      id: 1,
      run_type: "ai_task",
      task_id: "TASK-1",
      project_id: "proj-1",
      title: "Test run",
      description: "desc",
      branch_name: "feature/ai-TASK-1",
      status: "running",
      current_phase: "coding",
      retry_count: 0,
      error_message: null,
      pr_url: null,
      approved: null,
      rejection_reason: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
      started_at: "2024-01-01T00:00:01Z",
      completed_at: null,
      parent_run_id: null,
      workflow_template_id: null,
      max_retries: 3,
      workspace_path: "/workspaces/proj-1",
      repo_owner: "org",
      repo_name: "repo",
      default_branch: "main",
      task_source: "plane",
      git_provider: "gitea",
      task_source_meta: {},
      use_claude_api: false,
      workspace_config: null,
      workspace_result: null,
      planning_result: null,
      coding_results: null,
      test_results: null,
      review_result: null,
      approval_requested_at: null,
      phase_started_at: null,
      total_cost_usd: null,
      phase_executions: [],
    };
    expect(detail.max_retries).toBe(3);
    expect(detail.workspace_path).toBe("/workspaces/proj-1");
    expect(detail.phase_executions).toEqual([]);
  });

  it("PhaseExecution has required fields", () => {
    const pe: PhaseExecution = {
      id: 1,
      run_id: 1,
      phase_name: "coding",
      order_index: 3,
      trigger_mode: "auto",
      status: "completed",
      result: { ok: true },
      error_message: null,
      retry_count: 0,
      max_retries: 3,
      agent_override: null,
      notify_source: false,
      phase_config: null,
      started_at: "2024-01-01T00:00:01Z",
      completed_at: "2024-01-01T00:00:05Z",
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:05Z",
    };
    expect(pe.phase_name).toBe("coding");
    expect(pe.status).toBe("completed");
  });

  it("ProjectConfig has required fields", () => {
    const config: ProjectConfig = {
      project_id: "proj-1",
      project_slug: "my-project",
      repo_owner: "org",
      repo_name: "repo",
      default_branch: "main",
      task_source: "plane",
      git_provider: "gitea",
      has_git_provider_token: false,
      workspace_path: null,
      workspace_config: null,
      ai_config: null,
      workspace_server_id: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    };
    expect(config.project_id).toBe("proj-1");
  });

  it("Stats has all count fields", () => {
    const stats: Stats = {
      total_runs: 100,
      pending: 10,
      running: 5,
      awaiting_approval: 3,
      completed: 80,
      failed: 2,
    };
    expect(stats.total_runs).toBe(100);
    expect(stats.pending + stats.running + stats.awaiting_approval + stats.completed + stats.failed).toBe(100);
  });
});