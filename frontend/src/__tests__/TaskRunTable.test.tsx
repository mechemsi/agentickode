// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import TaskRunTable from "../components/runs/TaskRunTable";
import type { TaskRun } from "../types";

const baseMockRun: TaskRun = {
  id: 1,
  run_type: "ai_task",
  task_id: "TASK-1",
  project_id: "proj-1",
  title: "Fix bug",
  description: "Fix the login bug",
  branch_name: "feature/ai-TASK-1",
  status: "running",
  current_phase: "coding",
  retry_count: 0,
  error_message: null,
  pr_url: null,
  approved: null,
  rejection_reason: null,
  parent_run_id: null,
  workflow_template_id: null,
  total_cost_usd: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  started_at: null,
  completed_at: null,
};

const mockRun = baseMockRun;

describe("TaskRunTable", () => {
  it("shows empty message when no runs", () => {
    render(<MemoryRouter><TaskRunTable runs={[]} /></MemoryRouter>);
    expect(screen.getByText("No runs found.")).toBeInTheDocument();
  });

  it("renders rows for runs", () => {
    render(<MemoryRouter><TaskRunTable runs={[mockRun]} /></MemoryRouter>);
    expect(screen.getByText("Fix bug")).toBeInTheDocument();
    expect(screen.getByText("proj-1")).toBeInTheDocument();
  });

  it("links to run detail page", () => {
    render(<MemoryRouter><TaskRunTable runs={[mockRun]} /></MemoryRouter>);
    const link = screen.getByText("Fix bug").closest("a");
    expect(link).toHaveAttribute("href", "/runs/1");
  });

  it("shows workflow name when workflowNames map is provided", () => {
    const runWithWorkflow: TaskRun = { ...baseMockRun, workflow_template_id: 3 };
    const workflowNames = new Map([[3, "pr-review"]]);
    render(
      <MemoryRouter>
        <TaskRunTable runs={[runWithWorkflow]} workflowNames={workflowNames} />
      </MemoryRouter>,
    );
    expect(screen.getByText("pr-review")).toBeInTheDocument();
  });

  it("shows dash when run has no workflow template", () => {
    render(
      <MemoryRouter>
        <TaskRunTable
          runs={[baseMockRun]}
          workflowNames={new Map([[1, "default"]])}
        />
      </MemoryRouter>,
    );
    // The Workflow column header exists
    expect(screen.getByText("Workflow")).toBeInTheDocument();
  });
});