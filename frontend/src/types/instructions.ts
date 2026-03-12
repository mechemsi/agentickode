// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface ProjectInstruction {
  id: number;
  project_id: string;
  phase_name: string;
  content: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectSecret {
  id: number;
  project_id: string;
  name: string;
  inject_as: string;
  phase_scope: string | null;
  created_at: string;
  updated_at: string;
}

export interface InstructionVersion {
  id: number;
  instruction_id: number;
  content: string;
  changed_at: string;
  change_summary: string | null;
}

export interface PromptPreview {
  system_prompt_section: string;
  secrets_injected: string[];
}