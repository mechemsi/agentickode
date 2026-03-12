// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type {
  PhaseInfo,
  WorkflowTemplate,
  WorkflowTemplateCreate,
  WorkflowTemplateUpdate,
} from "../types";
import { get, post, put, httpDelete } from "./client";

export const getPhases = () => get<PhaseInfo[]>("/phases");

export const getWorkflowTemplates = () =>
  get<WorkflowTemplate[]>("/workflow-templates");

export const getWorkflowTemplate = (id: number) =>
  get<WorkflowTemplate>(`/workflow-templates/${id}`);

export const createWorkflowTemplate = (data: WorkflowTemplateCreate) =>
  post<WorkflowTemplate>("/workflow-templates", data);

export const updateWorkflowTemplate = (
  id: number,
  data: WorkflowTemplateUpdate,
) => put<WorkflowTemplate>(`/workflow-templates/${id}`, data);

export const deleteWorkflowTemplate = (id: number) =>
  httpDelete(`/workflow-templates/${id}`);

export const matchWorkflowTemplate = (labels: string[]) =>
  post<WorkflowTemplate>("/workflow-templates/match", { labels });