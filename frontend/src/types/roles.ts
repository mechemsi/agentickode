// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface RoleAssignment {
  id: number;
  role: string;
  provider_type: "ollama" | "agent";
  ollama_server_id: number | null;
  model_name: string | null;
  agent_name: string | null;
  workspace_server_id: number | null;
  workspace_server_name: string | null;
  ollama_server_name: string | null;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface RoleAssignmentInput {
  role: string;
  provider_type: "ollama" | "agent";
  ollama_server_id?: number | null;
  model_name?: string | null;
  agent_name?: string | null;
  workspace_server_id?: number | null;
  priority?: number;
}