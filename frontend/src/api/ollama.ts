// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type {
  GpuStatusResponse,
  OllamaServer,
  OllamaServerCreate,
  PreloadRequest,
  PreloadResult,
  RunningModelsResponse,
} from "../types";
import { get, post, put, httpDelete } from "./client";

export const getOllamaServers = () => get<OllamaServer[]>("/ollama-servers");

export const createOllamaServer = (data: OllamaServerCreate) =>
  post<OllamaServer>("/ollama-servers", data);

export const updateOllamaServer = (
  id: number,
  data: Partial<OllamaServerCreate>,
) => put<OllamaServer>(`/ollama-servers/${id}`, data);

export const deleteOllamaServer = (id: number) =>
  httpDelete(`/ollama-servers/${id}`);

export const refreshOllamaModels = (id: number) =>
  post<OllamaServer>(`/ollama-servers/${id}/refresh-models`);

export const getGpuStatus = () =>
  get<GpuStatusResponse>("/ollama-servers/gpu-status");

export const getRunningModels = (id: number) =>
  get<RunningModelsResponse>(`/ollama-servers/${id}/running`);

export const preloadModel = (id: number, data: PreloadRequest) =>
  post<PreloadResult>(`/ollama-servers/${id}/preload`, data);

export const unloadModel = (id: number, model: string) =>
  post<PreloadResult>(`/ollama-servers/${id}/unload`, { model });