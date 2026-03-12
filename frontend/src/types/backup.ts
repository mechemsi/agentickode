// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export type SecretMode = "plaintext" | "redacted" | "encrypted";
export type ConflictResolution = "skip" | "overwrite";

export interface ExportRequest {
  entity_types?: string[];
  secret_mode: SecretMode;
  encryption_password?: string;
  project_id?: string;
}

export interface ImportOptions {
  entity_types?: string[];
  conflict_resolution: ConflictResolution;
  encryption_password?: string;
}

export interface PreviewItemAction {
  match_key: Record<string, string>;
  action: "create" | "update";
}

export interface PreviewResult {
  entities: Record<string, PreviewItemAction[]>;
}

export interface ImportEntityResult {
  created: number;
  updated: number;
  skipped: number;
}

export interface ImportResult {
  entities: Record<string, ImportEntityResult>;
}