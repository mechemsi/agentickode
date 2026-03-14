// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export const AGENT_NAMES = [
  "claude",
  "codex",
  "opencode",
  "aider",
  "gemini",
  "kimi",
  "openhands",
] as const;
export type AgentName = (typeof AGENT_NAMES)[number];

export interface RoleConfig {
  id: number;
  agent_name: string;
  display_name: string;
  description: string;
  system_prompt: string;
  user_prompt_template: string;
  phase_binding: string | null;
  is_system: boolean;
  default_temperature: number;
  default_num_predict: number;
  extra_params: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RolePromptOverride {
  id: number;
  role_config_id: number;
  cli_agent_name: string;
  system_prompt: string | null;
  user_prompt_template: string | null;
  minimal_mode: boolean;
  extra_params: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface RolePromptOverrideIn {
  system_prompt: string | null;
  user_prompt_template: string | null;
  minimal_mode: boolean;
  extra_params: Record<string, unknown>;
}

export interface RoleConfigCreate {
  agent_name: string;
  display_name: string;
  description?: string;
  system_prompt?: string;
  user_prompt_template?: string;
  phase_binding?: string | null;
  default_temperature?: number;
  default_num_predict?: number;
  extra_params?: Record<string, unknown>;
}

export interface RoleConfigUpdate {
  display_name?: string;
  description?: string;
  system_prompt?: string;
  user_prompt_template?: string;
  phase_binding?: string | null;
  default_temperature?: number;
  default_num_predict?: number;
  extra_params?: Record<string, unknown>;
}

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