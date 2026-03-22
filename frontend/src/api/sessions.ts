// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { get, post, httpDelete } from "./client";
import type { CliSession, CliSessionCreate } from "../types/sessions";

export async function createSession(body: CliSessionCreate): Promise<CliSession> {
  return post("/sessions", body);
}

export async function listSessions(params?: {
  server_id?: number;
  project_id?: string;
  status?: string;
}): Promise<CliSession[]> {
  const q = new URLSearchParams();
  if (params?.server_id) q.set("server_id", String(params.server_id));
  if (params?.project_id) q.set("project_id", params.project_id);
  if (params?.status) q.set("status", params.status);
  const qs = q.toString();
  return get(`/sessions${qs ? `?${qs}` : ""}`);
}

export async function getSession(id: number): Promise<CliSession> {
  return get(`/sessions/${id}`);
}

export async function closeSession(id: number): Promise<void> {
  return httpDelete(`/sessions/${id}`);
}

export async function sendToSession(
  id: number,
  message: string,
): Promise<{ success: boolean; output: string | null }> {
  return post(`/sessions/${id}/send`, { message });
}

export async function captureSession(
  id: number,
  lines = 50,
): Promise<{ output: string; lines: number }> {
  return get(`/sessions/${id}/capture?lines=${lines}`);
}

export async function listServerSessions(serverId: number): Promise<CliSession[]> {
  return get(`/workspace-servers/${serverId}/sessions`);
}
