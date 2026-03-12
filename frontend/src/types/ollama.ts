// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface OllamaServer {
  id: number;
  name: string;
  url: string;
  status: string;
  last_seen_at: string | null;
  error_message: string | null;
  cached_models: Array<Record<string, unknown>> | null;
  created_at: string;
  updated_at: string;
}

export interface OllamaServerCreate {
  name: string;
  url: string;
}

export interface RunningModel {
  name: string;
  model?: string;
  size: number;
  size_vram: number;
  digest?: string;
  expires_at?: string;
  details?: {
    parent_model?: string;
    format?: string;
    family?: string;
    families?: string[];
    parameter_size?: string;
    quantization_level?: string;
  };
}

export interface RunningModelsResponse {
  server_id: number;
  server_name: string;
  server_url: string;
  status: string;
  models: RunningModel[];
  error: string | null;
}

export interface GpuStatusResponse {
  servers: RunningModelsResponse[];
}

export interface PreloadRequest {
  model: string;
  keep_alive: string | number;
}

export interface PreloadResult {
  success: boolean;
  model: string;
  error: string | null;
}