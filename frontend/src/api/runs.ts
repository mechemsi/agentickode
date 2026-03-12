// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type {
  AgentInvocation,
  AnalyticsSummary,
  PhaseExecution,
  Stats,
  TaskLog,
  TaskRun,
  TaskRunDetail,
} from "../types";
import { get, post } from "./client";

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface RunsQueryParams {
  status?: string;
  project_id?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}

export const getRuns = (params?: RunsQueryParams | string) => {
  if (typeof params === "string") {
    // Legacy compat: raw query string
    return get<PaginatedResponse<TaskRun>>(`/runs${params ? `?${params}` : ""}`);
  }
  const qs = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "" && v !== null) qs.set(k, String(v));
    }
  }
  const s = qs.toString();
  return get<PaginatedResponse<TaskRun>>(`/runs${s ? `?${s}` : ""}`);
};

export const createRun = (data: {
  project_id: string;
  title: string;
  description?: string;
  workflow_template_id?: number | null;
  labels?: string[];
  run_type?: string;
  agent_override?: string | null;
  workspace_server_id?: number | null;
  phase_overrides?: Record<string, Record<string, unknown>> | null;
  issue_number?: number | null;
  issue_url?: string | null;
  skip_schedule?: boolean;
}) =>
  post<{ id: number; status: string; title: string; project_id: string; branch_name: string }>(
    "/runs",
    data,
  );

export const getRun = (id: number) => get<TaskRunDetail>(`/runs/${id}`);
export const approveRun = (id: number) => post(`/runs/${id}/approve`);
export const rejectRun = (id: number, reason: string) =>
  post(`/runs/${id}/reject`, { reason });
export const retryRun = (id: number) => post(`/runs/${id}/retry`);
export const restartRun = (id: number) => post(`/runs/${id}/restart`);
export const cancelRun = (id: number) => post(`/runs/${id}/cancel`);
export const getStats = () => get<Stats>("/stats");
export const getAnalytics = (days = 14) =>
  get<AnalyticsSummary>(`/analytics/summary?days=${days}`);

export const getRunLogs = (
  id: number,
  opts?: { afterId?: number; phase?: string },
) => {
  const params = new URLSearchParams();
  if (opts?.afterId) params.set("after_id", String(opts.afterId));
  if (opts?.phase) params.set("phase", opts.phase);
  const qs = params.toString();
  return get<TaskLog[]>(`/runs/${id}/logs${qs ? `?${qs}` : ""}`);
};

export const getRunPhases = (id: number) =>
  get<PhaseExecution[]>(`/runs/${id}/phases`);

export const advancePhase = (runId: number, phaseName: string) =>
  post(`/runs/${runId}/phases/${encodeURIComponent(phaseName)}/advance`);

export const getRunInvocations = (id: number, sessionId?: string) => {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return get<AgentInvocation[]>(`/runs/${id}/invocations${qs}`);
};

export const getInvocationDetail = (runId: number, invocationId: number) =>
  get<AgentInvocation & { prompt_text?: string; response_text?: string; system_prompt_text?: string }>(
    `/runs/${runId}/invocations/${invocationId}`,
  );

export const runTerminalAction = (runId: number, action: string) =>
  post<{ status: string }>(`/runs/${runId}/terminal-action`, { action });

export const reviewPlan = (
  runId: number,
  payload: {
    action: "approve" | "reject";
    modified_subtasks?: Record<string, unknown>[] | null;
    rejection_reason?: string | null;
  },
) => post<{ status: string }>(`/runs/${runId}/plan-review`, payload);

export const pickComparisonWinner = (runId: number, winner: "a" | "b") =>
  post<{ status: string; winner: string; agent_name: string; branch: string }>(
    `/runs/${runId}/comparison/pick-winner`,
    { winner },
  );