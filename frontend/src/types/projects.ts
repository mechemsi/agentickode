// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface ThresholdRule {
  metric: string;
  operator: "<" | ">" | "==" | "<=" | ">=";
  value: number;
  task: string;
}

export interface AutonomyConfig {
  execution_mode: "structured" | "autonomous" | "hybrid" | "multi_agent";
  plan_approval: "none" | "show_and_continue" | "require_approval" | "adaptive";
  adaptive_max_files: number;
  merge_mode: "pr_only" | "auto_merge" | "risk_based";
  auto_merge_max_files: number;
  auto_merge_require_green_ci: boolean;
  allow_agent_followups: boolean;
  max_followup_depth: number;
  threshold_rules: ThresholdRule[];
}

export interface ProjectConfig {
  project_id: string;
  project_slug: string;
  repo_owner: string;
  repo_name: string;
  default_branch: string;
  task_source: string;
  git_provider: string;
  workspace_config: Record<string, unknown> | null;
  ai_config: Record<string, unknown> | null;
  workspace_server_ids: number[];
  workspace_path: string | null;
  local_path: string | null;
  worker_user_override: string | null;
  has_git_provider_token: boolean;
  autonomy_config: AutonomyConfig | null;
  integration_config: Record<string, unknown>;
  poll_enabled: boolean;
  poll_interval_minutes: number;
  last_polled_at: string | null;
  next_poll_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GitUrlParseResponse {
  provider: string;
  owner: string;
  repo: string;
  host: string;
  default_branch: string;
  suggested_slug: string;
  suggested_id: string;
  provider_confirmed: boolean;
}

export interface TestConnectionResponse {
  success: boolean;
  error?: string;
}

export interface WorkspaceReadinessItem {
  server_id: number;
  server_name: string;
  status: "ready" | "not_cloned" | "error" | "unreachable";
  path: string | null;
  error: string | null;
}

export interface WorkspaceReadinessResponse {
  project_id: string;
  workspaces: WorkspaceReadinessItem[];
}

export interface GitIssue {
  number: number;
  title: string;
  body: string;
  labels: string[];
  url: string;
  state: string;
}