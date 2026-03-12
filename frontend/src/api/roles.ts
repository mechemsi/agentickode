// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type { RoleAssignment, RoleAssignmentInput } from "../types";
import { get, put, httpDelete } from "./client";

export const getRoleAssignments = (scopeServerId?: number) =>
  get<RoleAssignment[]>(
    `/role-assignments${scopeServerId != null ? `?scope_server_id=${scopeServerId}` : ""}`,
  );

export const updateRoleAssignments = (assignments: RoleAssignmentInput[]) =>
  put<RoleAssignment[]>("/role-assignments", assignments);

export const deleteRoleAssignment = (id: number) =>
  httpDelete(`/role-assignments/${id}`);