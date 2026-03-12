// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

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
  workspace_server_id: number | null;
  workspace_path: string | null;
  has_git_provider_token: boolean;
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