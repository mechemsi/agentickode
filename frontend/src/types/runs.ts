// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface TaskRun {
  id: number;
  run_type: string;
  task_id: string;
  project_id: string;
  title: string;
  description: string;
  branch_name: string;
  status: string;
  current_phase: string | null;
  retry_count: number;
  error_message: string | null;
  pr_url: string | null;
  approved: boolean | null;
  rejection_reason: string | null;
  parent_run_id: number | null;
  flow_prompt_id: number | null;
  total_cost_usd: number | null;
  execution_mode: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface TaskRunDetail extends TaskRun {
  max_retries: number;
  workspace_path: string;
  repo_owner: string;
  repo_name: string;
  default_branch: string;
  task_source: string;
  git_provider: string;
  task_source_meta: Record<string, unknown>;
  use_claude_api: boolean;
  workspace_config: Record<string, unknown> | null;
  workspace_result: Record<string, unknown> | null;
  planning_result: Record<string, unknown> | null;
  coding_results: Record<string, unknown> | null;
  test_results: Record<string, unknown> | null;
  review_result: Record<string, unknown> | null;
  approval_requested_at: string | null;
  phase_started_at: string | null;
}

export interface TaskLog {
  id: number;
  run_id: number;
  timestamp: string;
  level: string;
  phase: string | null;
  message: string;
  metadata_?: Record<string, unknown> | null;
}