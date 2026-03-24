// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface Episode {
  id: number;
  episode_number: number;
  status: 'running' | 'completed' | 'stalled' | 'failed' | 'recovered';
  turn_count: number;
  tokens_used: number;
  context_usage_pct: number;
  git_checkpoint_sha: string | null;
  started_at: string | null;
  completed_at: string | null;
  exit_code: number | null;
  summary: string | null;
}

export interface AgentStreamEvent {
  type: 'progress' | 'done' | 'error';
  turns?: number;
  context_pct?: number;
  completed?: boolean;
  result?: string;
  status?: string;
  error?: string;
}
