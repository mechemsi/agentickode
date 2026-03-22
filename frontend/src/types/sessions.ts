// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface CliSession {
  id: number;
  session_id: string;
  workspace_server_id: number;
  server_name?: string | null;
  project_id: string | null;
  task_run_id: number | null;
  agent_name: string;
  user_context: string;
  workspace_path: string | null;
  display_name: string | null;
  tmux_session: string;
  status: "starting" | "active" | "idle" | "detached" | "closed" | "error";
  remote_control_enabled: boolean;
  started_at: string;
  last_activity_at: string;
  closed_at: string | null;
}

export interface CliSessionCreate {
  workspace_server_id: number;
  agent_name: string;
  user_context?: string;
  project_id?: string | null;
  workspace_path?: string | null;
  display_name?: string | null;
}
