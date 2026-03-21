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
  has_git_provider_token: boolean;
  autonomy_config: AutonomyConfig | null;
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

export interface GitIssue {
  number: number;
  title: string;
  body: string;
  labels: string[];
  url: string;
  state: string;
}