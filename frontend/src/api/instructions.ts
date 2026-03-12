// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type { InstructionVersion, ProjectInstruction, ProjectSecret, PromptPreview } from "../types";
import { get, post, put, httpDelete } from "./client";

const enc = encodeURIComponent;

export const getInstructions = (projectId: string) =>
  get<ProjectInstruction[]>(`/projects/${enc(projectId)}/instructions`);

export const upsertGlobalInstruction = (projectId: string, content: string) =>
  put<ProjectInstruction>(`/projects/${enc(projectId)}/instructions`, { content });

export const upsertPhaseInstruction = (projectId: string, phase: string, content: string) =>
  put<ProjectInstruction>(`/projects/${enc(projectId)}/instructions/${enc(phase)}`, { content });

export const deleteInstruction = (projectId: string, phase: string) =>
  httpDelete(`/projects/${enc(projectId)}/instructions/${enc(phase)}`);

export const getInstructionVersions = (projectId: string) =>
  get<InstructionVersion[]>(`/projects/${enc(projectId)}/instructions/versions`);

export const getSecrets = (projectId: string) =>
  get<ProjectSecret[]>(`/projects/${enc(projectId)}/secrets`);

export const createSecret = (projectId: string, data: { name: string; value: string; inject_as: string; phase_scope?: string | null }) =>
  post<ProjectSecret>(`/projects/${enc(projectId)}/secrets`, data);

export const updateSecret = (projectId: string, secretId: number, data: { value?: string; inject_as?: string; phase_scope?: string | null }) =>
  put<ProjectSecret>(`/projects/${enc(projectId)}/secrets/${secretId}`, data);

export const deleteSecret = (projectId: string, secretId: number) =>
  httpDelete(`/projects/${enc(projectId)}/secrets/${secretId}`);

export const previewPrompt = (projectId: string, phaseName: string) =>
  post<PromptPreview>(`/projects/${enc(projectId)}/instructions/preview`, { phase_name: phaseName });