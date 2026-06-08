// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

// Hard-coded allowlist of agents shown in pickers (chat session, step
// editor, agent install, etc.). The backend may still know about more
// agents in the DB — this is the user-facing surface only. To re-show
// an agent, add it here and make sure its AgentSettings row exists.
export const AGENT_NAMES = [
  "claude",
  "codex",
  "opencode",
] as const;
export type AgentName = (typeof AGENT_NAMES)[number];

/** Set form of AGENT_NAMES for ``.has()`` checks when filtering API responses. */
export const VISIBLE_AGENTS: ReadonlySet<string> = new Set(AGENT_NAMES);

export interface AgentSettings {
  id: number;
  agent_name: string;
  display_name: string;
  description: string;
  supports_session: boolean;
  default_timeout: number;
  max_retries: number;
  environment_vars: Record<string, string>;
  cli_flags: Record<string, string | boolean>;
  command_templates: Record<string, string | boolean>;
  enabled: boolean;
  agent_type: string;
  install_cmd: string | null;
  post_install_cmd: string | null;
  check_cmd: string | null;
  prereq_check: string | null;
  prereq_name: string | null;
  needs_non_root: boolean;
  consolidated_default: boolean;
  agent_creates_pr: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgentInvocation {
  id: number;
  run_id: number;
  phase_execution_id: number | null;
  workspace_server_id: number | null;
  agent_name: string;
  phase_name: string | null;
  subtask_index: number | null;
  subtask_title: string | null;
  prompt_chars: number;
  response_chars: number;
  exit_code: number | null;
  files_changed: string[] | null;
  duration_seconds: number | null;
  estimated_tokens_in: number | null;
  estimated_tokens_out: number | null;
  estimated_cost_usd: number | null;
  status: string;
  error_message: string | null;
  session_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  metadata_: Record<string, unknown> | null;
}

export interface AgentInvocationDetail extends AgentInvocation {
  prompt_text: string | null;
  response_text: string | null;
  system_prompt_text: string | null;
}

export interface AgentInstallStatus {
  agent_name: string;
  display_name: string;
  description: string;
  agent_type: string;
  installed: boolean;
  version: string | null;
  path: string | null;
  authenticated: boolean | null;
  auth_email: string | null;
  auth_method: string | null;
}

export interface UserAgentStatus {
  user: string;
  agents: AgentInstallStatus[];
}

export interface AgentManagementStatus {
  agents: AgentInstallStatus[];
  by_user: UserAgentStatus[];
}

export interface AgentInstallResult {
  success: boolean;
  agent_name: string;
  message: string | null;
  error: string | null;
  output: string | null;
}