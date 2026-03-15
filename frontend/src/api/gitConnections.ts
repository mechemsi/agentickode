// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type { GitConnection, GitConnectionCreate, GitConnectionTestResult } from "../types";
import { get, post, put, httpDelete } from "./client";

function buildQuery(params?: Record<string, unknown>): string {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) q.set(k, String(v));
  }
  const qs = q.toString();
  return qs ? `?${qs}` : "";
}

export const getGitConnections = (params?: {
  workspace_server_id?: number;
  project_id?: string;
  scope?: string;
}) => get<GitConnection[]>(`/git-connections${buildQuery(params)}`);

export const createGitConnection = (data: GitConnectionCreate) =>
  post<GitConnection>("/git-connections", data);

export const updateGitConnection = (id: number, data: Partial<GitConnectionCreate>) =>
  put<GitConnection>(`/git-connections/${id}`, data);

export const deleteGitConnection = (id: number) =>
  httpDelete(`/git-connections/${id}`);

export const testGitConnection = (id: number) =>
  post<GitConnectionTestResult>(`/git-connections/${id}/test`, {});
