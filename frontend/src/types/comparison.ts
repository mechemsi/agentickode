// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface ComparisonAgentResult {
  agent_name: string;
  branch: string;
  results: Array<{
    subtask_title: string;
    files_changed: string[];
    exit_code: number | string;
  }>;
  total_cost_usd: number | null;
  total_duration_seconds: number | null;
  invocation_ids: number[];
}

export interface ComparisonResults {
  comparison_mode: true;
  base_commit: string;
  agents: {
    a: ComparisonAgentResult;
    b: ComparisonAgentResult;
  };
  winner: "a" | "b" | null;
}