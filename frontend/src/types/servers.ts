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
  server_type?: string;
  port: number;
  username: string;
  ssh_key_path: string | null;
  workspace_root: string;
  workspace_folders?: string[] | null;
  status: string;
  last_seen_at: string | null;
  error_message: string | null;
  worker_user: string | null;
  worker_user_status: string | null;
  worker_user_password: string | null;
  setup_log: Record<string, SetupStepEntry> | null;
  agent_count: number;
  project_count: number;
  server_group_id: number | null;
  server_group_name: string | null;
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
  workspace_folders?: string[] | null;
  setup_password?: string;
}

export interface GhCliCheckResult {
  installed: boolean;
  auth_ok: boolean;
  auth_user: string | null;
  error: string | null;
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

// Docker management types
export interface DockerContainer {
  id: string;
  names: string;
  image: string;
  status: string;
  state: string;
  ports: string;
  created_at: string | null;
  size: string | null;
}

export interface DockerImage {
  id: string;
  repository: string;
  tag: string;
  size: string;
  created_at: string | null;
}

export interface DockerVolume {
  name: string;
  driver: string;
  mountpoint: string | null;
}

export interface DockerNetwork {
  id: string;
  name: string;
  driver: string;
  scope: string;
}

export interface DockerComposeStack {
  name: string;
  status: string;
  config_files: string | null;
}

export interface DockerOverview {
  containers: DockerContainer[];
  images: DockerImage[];
  volumes: DockerVolume[];
  networks: DockerNetwork[];
  stacks: DockerComposeStack[];
  disk_usage: string;
}

export interface PruneResult {
  output: string;
}

export interface ServerGroup {
  id: number;
  name: string;
  description: string | null;
  git_provider_type: string | null;
  has_git_token: boolean;
  server_count: number;
  created_at: string;
  updated_at: string;
}

export interface ServerGroupDetail extends ServerGroup {
  servers: { id: number; name: string; hostname: string; status: string }[];
}

export interface ServerGroupCreate {
  name: string;
  description?: string;
}