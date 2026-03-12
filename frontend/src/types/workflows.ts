// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface PhaseInfo {
  name: string;
  description: string;
  default_role: string | null;
  default_agent_mode: "generate" | "task" | null;
}

export interface LabelRule {
  match_all: string[];
  match_any: string[];
}

export interface PhaseConfig {
  phase_name: string;
  enabled: boolean;
  role: string | null;
  uses_agent?: boolean | null;
  agent_mode?: "generate" | "task" | null;
  trigger_mode: string;
  notify_source: boolean;
  timeout_seconds: number | null;
  params: Record<string, unknown>;
  cli_flags?: Record<string, string> | null;
  environment_vars?: Record<string, string> | null;
  command_templates?: Record<string, string> | null;
}

export interface WorkflowTemplate {
  id: number;
  name: string;
  description: string;
  label_rules: LabelRule[];
  phases: PhaseConfig[];
  is_default: boolean;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowTemplateCreate {
  name: string;
  description?: string;
  label_rules?: LabelRule[];
  phases?: PhaseConfig[];
  is_default?: boolean;
}

export interface WorkflowTemplateUpdate {
  name?: string;
  description?: string;
  label_rules?: LabelRule[];
  phases?: PhaseConfig[];
}