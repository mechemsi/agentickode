// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface PhaseDurationStat {
  phase_name: string;
  avg_seconds: number;
  count: number;
}

export interface AgentStat {
  agent_name: string;
  total_runs: number;
  success_rate: number;
  avg_duration_seconds: number;
}

export interface DailyRunCount {
  date: string;
  count: number;
}

export interface AgentCostStat {
  agent_name: string;
  cost_usd: number;
}

export interface CostStats {
  total_cost_usd: number;
  total_tokens_in: number;
  total_tokens_out: number;
  avg_cost_per_run_usd: number;
  cost_by_agent: AgentCostStat[];
}

export interface AnalyticsSummary {
  success_rate: number;
  avg_duration_seconds: number;
  total_runs: number;
  runs_by_status: Record<string, number>;
  avg_phase_durations: PhaseDurationStat[];
  agent_stats: AgentStat[];
  runs_over_time: DailyRunCount[];
  cost_stats?: CostStats;
}

export interface Stats {
  total_runs: number;
  pending: number;
  running: number;
  awaiting_approval: number;
  completed: number;
  failed: number;
}