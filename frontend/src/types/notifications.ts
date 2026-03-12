// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface NotificationChannel {
  id: number;
  name: string;
  channel_type: "telegram" | "slack" | "discord" | "webhook";
  config: Record<string, string>;
  events: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationChannelCreate {
  name: string;
  channel_type: string;
  config: Record<string, string>;
  events: string[];
  enabled?: boolean;
}

export interface NotificationTestResult {
  success: boolean;
  error: string | null;
}

export const NOTIFICATION_EVENTS = [
  "run_started",
  "run_completed",
  "run_failed",
  "approval_requested",
  "phase_completed",
  "phase_failed",
  "phase_waiting",
] as const;

export const CHANNEL_TYPES = [
  "telegram",
  "slack",
  "discord",
  "webhook",
] as const;