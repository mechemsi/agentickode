// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type {
  AgentInvocation,
  DockerContainer,
  DockerComposeStack,
  DockerImage,
  DockerNetwork,
  DockerOverview,
  DockerVolume,
  GhCliCheckResult,
  GitAccessStatus,
  ProjectConfig,
  PruneResult,
  ServerGroup,
  ServerGroupCreate,
  ServerGroupDetail,
  SSHTestResult,
  ScanResult,
  WorkspaceServer,
  WorkspaceServerCreate,
  WorkspaceServerDetail,
} from "../types";
import { get, post, put, httpDelete } from "./client";

export const getWorkspaceServers = (check?: boolean) =>
  get<WorkspaceServer[]>(`/workspace-servers${check ? "?check=true" : ""}`);

export const getWorkspaceServer = (id: number) =>
  get<WorkspaceServerDetail>(`/workspace-servers/${id}`);

export const createWorkspaceServer = (data: WorkspaceServerCreate) =>
  post<WorkspaceServerDetail>("/workspace-servers", data);

export const updateWorkspaceServer = (
  id: number,
  data: Partial<WorkspaceServerCreate>,
) => put<WorkspaceServer>(`/workspace-servers/${id}`, data);

export const deleteWorkspaceServer = (id: number) =>
  httpDelete(`/workspace-servers/${id}`);

export const testWorkspaceServer = (id: number) =>
  post<SSHTestResult>(`/workspace-servers/${id}/test`);

export const scanWorkspaceServer = (id: number) =>
  post<ScanResult>(`/workspace-servers/${id}/scan`);

export const deployKeyToServer = (id: number, password: string) =>
  post<SSHTestResult>(`/workspace-servers/${id}/deploy-key`, { password });

export const getProjectsByServer = (serverId: number) =>
  get<ProjectConfig[]>(`/workspace-servers/${serverId}/projects`);

export async function listServerInvocations(
  serverId: number,
  params?: { agent_name?: string; phase_name?: string; status?: string; limit?: number; offset?: number },
): Promise<AgentInvocation[]> {
  const q = new URLSearchParams();
  if (params?.agent_name) q.set("agent_name", params.agent_name);
  if (params?.phase_name) q.set("phase_name", params.phase_name);
  if (params?.status) q.set("status", params.status);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const qs = q.toString();
  return get<AgentInvocation[]>(`/workspace-servers/${serverId}/invocations${qs ? `?${qs}` : ""}`);
}

export const getServerSetupLog = (id: number) =>
  get<Record<string, unknown>>(`/workspace-servers/${id}/setup-log`);

export const retryServerSetup = (id: number, setupPassword?: string) =>
  post<{ status: string }>(`/workspace-servers/${id}/retry-setup`, setupPassword ? { setup_password: setupPassword } : {});

export const checkGitAccess = (id: number, customHosts?: string[]) =>
  post<GitAccessStatus>(`/workspace-servers/${id}/git-access/check`, customHosts?.length ? { custom_hosts: customHosts } : {});

export const generateGitKey = (id: number, force?: boolean) =>
  post<GitAccessStatus>(`/workspace-servers/${id}/git-access/generate-key`, force ? { force } : {});

export const syncGitKeys = (id: number) =>
  post<GitAccessStatus>(`/workspace-servers/${id}/git-access/sync-keys`, {});

export const checkGhCli = (id: number) =>
  post<GhCliCheckResult>(`/workspace-servers/${id}/git-access/check-gh`, {});

// --- Server Groups ---

export const getServerGroups = () =>
  get<ServerGroup[]>("/server-groups");

export const getServerGroup = (id: number) =>
  get<ServerGroupDetail>(`/server-groups/${id}`);

export const createServerGroup = (data: ServerGroupCreate) =>
  post<ServerGroup>("/server-groups", data);

export const updateServerGroup = (id: number, data: Partial<ServerGroupCreate>) =>
  put<ServerGroup>(`/server-groups/${id}`, data);

export const deleteServerGroup = (id: number) =>
  httpDelete(`/server-groups/${id}`);

export const setServerGroupToken = (id: number, git_token: string, git_provider_type: string) =>
  post<ServerGroup>(`/server-groups/${id}/set-token`, { git_token, git_provider_type });

export const deployServerGroupToken = (id: number) =>
  post<{ results: { server_id: number; name: string; success: boolean; error: string | null }[] }>(`/server-groups/${id}/deploy-token`);

export const deployServerGroupSSHKey = (id: number) =>
  post<{ public_key: string; results: { server_id: number; name: string; success: boolean; error: string | null }[] }>(`/server-groups/${id}/deploy-ssh-key`);

export const addServerToGroup = (groupId: number, serverId: number) =>
  post<{ status: string }>(`/server-groups/${groupId}/add-server/${serverId}`);

export const removeServerFromGroup = (groupId: number, serverId: number) =>
  httpDelete(`/server-groups/${groupId}/remove-server/${serverId}`);

// --- Docker Management ---

export const getDockerOverview = (serverId: number) =>
  get<DockerOverview>(`/workspace-servers/${serverId}/docker/overview`);

export const getDockerContainers = (serverId: number, all = true) =>
  get<DockerContainer[]>(`/workspace-servers/${serverId}/docker/containers?all=${all}`);

export const getDockerImages = (serverId: number) =>
  get<DockerImage[]>(`/workspace-servers/${serverId}/docker/images`);

export const getDockerVolumes = (serverId: number) =>
  get<DockerVolume[]>(`/workspace-servers/${serverId}/docker/volumes`);

export const getDockerNetworks = (serverId: number) =>
  get<DockerNetwork[]>(`/workspace-servers/${serverId}/docker/networks`);

export const getDockerStacks = (serverId: number) =>
  get<DockerComposeStack[]>(`/workspace-servers/${serverId}/docker/stacks`);

export const getContainerLogs = (serverId: number, containerId: string, tail = 100) =>
  get<{ logs: string }>(`/workspace-servers/${serverId}/docker/containers/${containerId}/logs?tail=${tail}`);

export const startDockerContainer = (serverId: number, containerId: string) =>
  post<PruneResult>(`/workspace-servers/${serverId}/docker/containers/${containerId}/start`);

export const stopDockerContainer = (serverId: number, containerId: string) =>
  post<PruneResult>(`/workspace-servers/${serverId}/docker/containers/${containerId}/stop`);

export const restartDockerContainer = (serverId: number, containerId: string) =>
  post<PruneResult>(`/workspace-servers/${serverId}/docker/containers/${containerId}/restart`);

export const removeDockerContainer = (serverId: number, containerId: string, force = false) =>
  httpDelete(`/workspace-servers/${serverId}/docker/containers/${containerId}?force=${force}`);

export const removeDockerImage = (serverId: number, imageId: string, force = false) =>
  httpDelete(`/workspace-servers/${serverId}/docker/images/${encodeURIComponent(imageId)}?force=${force}`);

export const dockerPrune = (serverId: number, target: string, all = false, includeVolumes = false) =>
  post<PruneResult>(`/workspace-servers/${serverId}/docker/prune`, { target, all, include_volumes: includeVolumes });

export const getDockerDiskUsage = (serverId: number) =>
  get<{ output: string }>(`/workspace-servers/${serverId}/docker/disk-usage`);