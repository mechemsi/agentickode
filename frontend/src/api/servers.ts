// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type {
  AgentInvocation,
  GitAccessStatus,
  ProjectConfig,
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