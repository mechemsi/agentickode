// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type { GitIssue, GitUrlParseResponse, ProjectConfig, TestConnectionResponse } from "../types";
import { BASE, get, post, put, httpDelete } from "./client";

export const getProjects = () => get<ProjectConfig[]>("/projects");

export const createProject = (data: Partial<ProjectConfig>) =>
  post<ProjectConfig>("/projects", data);

export const updateProject = (id: string, data: Partial<ProjectConfig>) =>
  put<ProjectConfig>(`/projects/${encodeURIComponent(id)}`, data);

export const deleteProject = (id: string) =>
  httpDelete(`/projects/${encodeURIComponent(id)}`);

export const parseGitUrl = (git_url: string, workspace_server_id?: number | null) =>
  post<GitUrlParseResponse>("/projects/parse-git-url", {
    git_url,
    ...(workspace_server_id ? { workspace_server_id } : {}),
  });

export const testConnection = (workspace_server_id: number, git_url: string) =>
  post<TestConnectionResponse>("/projects/test-connection", { workspace_server_id, git_url });

export async function getProjectIssues(projectId: string): Promise<GitIssue[]> {
  const res = await fetch(`${BASE}/projects/${encodeURIComponent(projectId)}/issues`);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch { /* ignore parse errors */ }
    throw new Error(detail);
  }
  return res.json();
}