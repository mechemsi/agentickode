// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface GitProviderStatus {
  host: string;
  name: string;
  connected: boolean;
  username: string | null;
  error: string | null;
}

export interface UserGitAccessStatus {
  user: string;
  has_key: boolean;
  public_key: string | null;
  key_type: string | null;
  providers: GitProviderStatus[];
}

export interface GitAccessStatus {
  has_key: boolean;
  public_key: string | null;
  key_type: string | null;
  providers: GitProviderStatus[];
  by_user: UserGitAccessStatus[];
}

export interface SSHKey {
  name: string;
  public_key: string | null;
  created_at: string;
  is_default: boolean;
}

export interface SSHKeyCreate {
  name: string;
  comment?: string;
}