// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type { SSHKey, SSHKeyCreate } from "../types";
import { get, post, put, httpDelete } from "./client";

export const getSSHKeys = () => get<SSHKey[]>("/ssh-keys");

export const createSSHKey = (data: SSHKeyCreate) =>
  post<SSHKey>("/ssh-keys", data);

export const deleteSSHKey = (name: string) =>
  httpDelete(`/ssh-keys/${encodeURIComponent(name)}`);

export const getAppSettings = () =>
  get<Record<string, unknown>>("/app-settings");

export const updateAppSetting = (key: string, value: unknown) =>
  put<{ key: string; value: unknown }>(`/app-settings/${encodeURIComponent(key)}`, { value });