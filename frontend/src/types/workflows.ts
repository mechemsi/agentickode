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

export type StepKind = "legacy_phase" | "bash" | "agent";

export type StepFailureMode = "fail" | "skip";

export interface PhaseConfig {
  phase_name: string;
  kind?: StepKind;
  enabled: boolean;
  role: string | null;
  uses_agent?: boolean | null;
  agent_mode?: "generate" | "task" | null;
  trigger_mode: string;
  failure_mode?: StepFailureMode;
  notify_source: boolean;
  timeout_seconds: number | null;
  params: Record<string, unknown>;
  cli_flags?: Record<string, string> | null;
  environment_vars?: Record<string, string> | null;
  command_templates?: Record<string, string> | null;
}

export interface StepKindParamSchema {
  type: string;
  required?: boolean;
  default?: unknown;
  enum?: string[];
  description?: string;
}

export interface StepKindDescriptor {
  kind: StepKind;
  description: string;
  /** Param-schema map for `bash` and `agent`. Absent for `legacy_phase`. */
  params_schema?: Record<string, StepKindParamSchema>;
  /** Discovered phase module names. Present only on `legacy_phase`. */
  values?: string[];
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