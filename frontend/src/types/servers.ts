// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface SetupStepEntry {
  status: string;
  error: string | null;
  timestamp: string;
}

export interface WorkspaceServer {
  id: number;
  name: string;
  hostname: string;
  port: number;
  username: string;
  ssh_key_path: string | null;
  workspace_root: string;
  status: string;
  last_seen_at: string | null;
  error_message: string | null;
  worker_user: string | null;
  worker_user_status: string | null;
  worker_user_password: string | null;
  setup_log: Record<string, SetupStepEntry> | null;
  agent_count: number;
  project_count: number;
  created_at: string;
  updated_at: string;
}

export interface DiscoveredAgent {
  id: number;
  agent_name: string;
  agent_type: string;
  path: string | null;
  version: string | null;
  available: boolean;
  discovered_at: string;
}

export interface WorkspaceServerDetail extends WorkspaceServer {
  agents: DiscoveredAgent[];
}

export interface WorkspaceServerCreate {
  name: string;
  hostname: string;
  port?: number;
  username?: string;
  ssh_key_path?: string;
  worker_user?: string;
  workspace_root?: string;
  setup_password?: string;
}

export interface SSHTestResult {
  success: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface ScanResult {
  agents_found: number;
  projects_found: number;
  projects_imported: number;
}

export interface DeployKeyRequest {
  password: string;
}

export interface WorkerUserSetupResult {
  success: boolean;
  username: string;
  status: string;
  agents: string[];
  error: string | null;
}

export interface WorkerUserStatus {
  username: string | null;
  status: string | null;
  error: string | null;
  agents: string[];
}