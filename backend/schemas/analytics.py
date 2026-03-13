# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from pydantic import BaseModel


class PhaseDurationStat(BaseModel):
    phase_name: str
    avg_seconds: float
    count: int


class AgentStat(BaseModel):
    agent_name: str
    total_runs: int
    success_rate: float
    avg_duration_seconds: float


class DailyRunCount(BaseModel):
    date: str
    count: int


class AgentCostStat(BaseModel):
    agent_name: str
    cost_usd: float


class CostStats(BaseModel):
    total_cost_usd: float
    total_tokens_in: int
    total_tokens_out: int
    avg_cost_per_run_usd: float
    cost_by_agent: list[AgentCostStat]


class AnalyticsSummary(BaseModel):
    success_rate: float
    avg_duration_seconds: float
    total_runs: int
    runs_by_status: dict[str, int]
    avg_phase_durations: list[PhaseDurationStat]
    agent_stats: list[AgentStat]
    runs_over_time: list[DailyRunCount]
    cost_stats: CostStats | None = None


class StatsResponse(BaseModel):
    total_runs: int
    pending: int
    running: int
    awaiting_approval: int
    completed: int
    failed: int
