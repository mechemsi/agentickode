// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type {
  RoleConfig,
  RoleConfigCreate,
  RoleConfigUpdate,
  RolePromptOverride,
  RolePromptOverrideIn,
} from "../types";
import { get, post, put, httpDelete } from "./client";

export const getRoleConfigs = () => get<RoleConfig[]>("/role-configs");

export const getRoleConfig = (name: string) =>
  get<RoleConfig>(`/role-configs/${encodeURIComponent(name)}`);

export const createRoleConfig = (data: RoleConfigCreate) =>
  post<RoleConfig>("/role-configs", data);

export const updateRoleConfig = (name: string, data: RoleConfigUpdate) =>
  put<RoleConfig>(`/role-configs/${encodeURIComponent(name)}`, data);

export const deleteRoleConfig = (name: string) =>
  httpDelete(`/role-configs/${encodeURIComponent(name)}`);

export const resetRoleConfig = (name: string) =>
  post<RoleConfig>(`/role-configs/${encodeURIComponent(name)}/reset`);

export const getPromptOverrides = (configName: string) =>
  get<RolePromptOverride[]>(
    `/role-configs/${encodeURIComponent(configName)}/overrides`,
  );

export const upsertPromptOverride = (
  configName: string,
  agentName: string,
  data: RolePromptOverrideIn,
) =>
  put<RolePromptOverride>(
    `/role-configs/${encodeURIComponent(configName)}/overrides/${encodeURIComponent(agentName)}`,
    data,
  );

export const deletePromptOverride = (configName: string, agentName: string) =>
  httpDelete(
    `/role-configs/${encodeURIComponent(configName)}/overrides/${encodeURIComponent(agentName)}`,
  );