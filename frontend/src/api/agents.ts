// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type {
  AgentInstallResult,
  AgentManagementStatus,
  AgentSettings,
  WorkerUserSetupResult,
  WorkerUserStatus,
} from "../types";
import { get, post, put } from "./client";

export const getAgents = () => get<AgentSettings[]>("/agents");

export const getAgent = (name: string) =>
  get<AgentSettings>(`/agents/${encodeURIComponent(name)}`);

export const updateAgent = (name: string, data: Partial<AgentSettings>) =>
  put<AgentSettings>(`/agents/${encodeURIComponent(name)}`, data);

export const getAgentAvailability = (name: string) =>
  get<{ workspace_server_id: number; version: string; path: string }[]>(
    `/agents/${encodeURIComponent(name)}/availability`,
  );

export const getSupportedAgents = () =>
  get<{ name: string; display_name: string; description: string; agent_type: string }[]>(
    "/supported-agents",
  );

export const getAgentStatus = (id: number) =>
  post<AgentManagementStatus>(`/workspace-servers/${id}/agents/status`);

export const installAgent = (id: number, agentName: string) =>
  post<AgentInstallResult>(`/workspace-servers/${id}/agents/install`, { agent_name: agentName });

export async function installAgentStream(
  serverId: number,
  agentName: string,
  onLine: (line: string, type: string) => void,
): Promise<void> {
  const res = await fetch(`/api/workspace-servers/${serverId}/agents/install-stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_name: agentName }),
  });
  if (!res.ok) throw new Error(`Install stream failed: ${res.status}`);
  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  // eslint-disable-next-line no-undef
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const msg = JSON.parse(line.slice(6));
        onLine(msg.line || "", msg.type);
      } catch {
        // skip malformed SSE lines
      }
    }
  }
}

export const installAgentForWorker = (id: number, agentName: string) =>
  post<AgentInstallResult>(`/workspace-servers/${id}/agents/install-worker`, { agent_name: agentName });

export const setupWorkerUser = (id: number, username = "coder") =>
  post<WorkerUserSetupResult>(`/workspace-servers/${id}/worker-user/setup`, { username });

export const getWorkerUserStatus = (id: number) =>
  post<WorkerUserStatus>(`/workspace-servers/${id}/worker-user/status`);

export const syncWorkerUser = (id: number) =>
  post<WorkerUserSetupResult>(`/workspace-servers/${id}/worker-user/sync`);

export const setWorkerUserPassword = (id: number, password: string) =>
  post<{ success: boolean; error: string | null }>(
    `/workspace-servers/${id}/worker-user/set-password`,
    { password },
  );