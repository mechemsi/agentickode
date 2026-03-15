// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface GitConnection {
  id: number;
  name: string;
  provider: string;
  base_url: string | null;
  scope: string;
  workspace_server_id: number | null;
  project_id: string | null;
  is_default: boolean;
  has_token: boolean;
  created_at: string;
  updated_at: string;
}

export interface GitConnectionCreate {
  name: string;
  provider: string;
  base_url?: string;
  token: string;
  scope: string;
  workspace_server_id?: number;
  project_id?: string;
  is_default?: boolean;
}

export interface GitConnectionTestResult {
  success: boolean;
  username: string | null;
  error: string | null;
}
