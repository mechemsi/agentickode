# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for run analytics queries."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentInvocation, PhaseExecution, TaskRun


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_summary(self, days: int = 14) -> dict[str, Any]:
        cutoff = datetime.utcnow() - timedelta(days=days)

        runs_by_status = await self._runs_by_status(cutoff)
        total = sum(runs_by_status.values())
        completed = runs_by_status.get("completed", 0)
        failed = runs_by_status.get("failed", 0)

        success_rate = (
            round(completed / (completed + failed) * 100, 1) if (completed + failed) > 0 else 0.0
        )

        avg_duration = await self._avg_duration(cutoff)
        phase_durations = await self._phase_durations(cutoff)
        agent_stats = await self._agent_stats(cutoff)
        runs_over_time = await self._runs_over_time(cutoff)
        cost_stats = await self._cost_stats(cutoff)

        return {
            "success_rate": success_rate,
            "avg_duration_seconds": avg_duration,
            "total_runs": total,
            "runs_by_status": runs_by_status,
            "avg_phase_durations": phase_durations,
            "agent_stats": agent_stats,
            "runs_over_time": runs_over_time,
            "cost_stats": cost_stats,
        }

    async def _runs_by_status(self, cutoff: datetime) -> dict[str, int]:
        result = await self.session.execute(
            select(TaskRun.status, func.count(TaskRun.id))
            .where(TaskRun.created_at >= cutoff)
            .group_by(TaskRun.status)
        )
        return {row[0]: row[1] for row in result.all()}

    async def _avg_duration(self, cutoff: datetime) -> float:
        """Average duration in seconds for completed runs (Python datetime math)."""
        result = await self.session.execute(
            select(TaskRun.started_at, TaskRun.completed_at).where(
                TaskRun.created_at >= cutoff,
                TaskRun.status == "completed",
                TaskRun.started_at.isnot(None),
                TaskRun.completed_at.isnot(None),
            )
        )
        rows = result.all()
        if not rows:
            return 0.0

        durations = []
        for started, completed in rows:
            if started and completed:
                delta = (completed - started).total_seconds()
                if delta >= 0:
                    durations.append(delta)

        return round(sum(durations) / len(durations), 1) if durations else 0.0

    async def _phase_durations(self, cutoff: datetime) -> list[dict[str, Any]]:
        """Average duration per phase (Python datetime math)."""
        result = await self.session.execute(
            select(
                PhaseExecution.phase_name,
                PhaseExecution.started_at,
                PhaseExecution.completed_at,
            ).where(
                PhaseExecution.created_at >= cutoff,
                PhaseExecution.status == "completed",
                PhaseExecution.started_at.isnot(None),
                PhaseExecution.completed_at.isnot(None),
            )
        )
        rows = result.all()

        phase_totals: dict[str, list[float]] = {}
        for phase_name, started, completed in rows:
            if started and completed:
                delta = (completed - started).total_seconds()
                if delta >= 0:
                    phase_totals.setdefault(phase_name, []).append(delta)

        return [
            {
                "phase_name": name,
                "avg_seconds": round(sum(vals) / len(vals), 1),
                "count": len(vals),
            }
            for name, vals in sorted(phase_totals.items())
        ]

    async def _agent_stats(self, cutoff: datetime) -> list[dict[str, Any]]:
        """Agent invocation stats with success rate and avg duration."""
        result = await self.session.execute(
            select(
                AgentInvocation.agent_name,
                AgentInvocation.status,
                AgentInvocation.duration_seconds,
            ).where(AgentInvocation.started_at >= cutoff)
        )
        rows = result.all()

        agent_data: dict[str, dict] = {}
        for agent_name, status, duration in rows:
            if agent_name not in agent_data:
                agent_data[agent_name] = {"total": 0, "success": 0, "durations": []}
            agent_data[agent_name]["total"] += 1
            if status == "success":
                agent_data[agent_name]["success"] += 1
            if duration is not None:
                agent_data[agent_name]["durations"].append(duration)

        return [
            {
                "agent_name": name,
                "total_runs": data["total"],
                "success_rate": round(data["success"] / data["total"] * 100, 1)
                if data["total"] > 0
                else 0.0,
                "avg_duration_seconds": round(sum(data["durations"]) / len(data["durations"]), 1)
                if data["durations"]
                else 0.0,
            }
            for name, data in sorted(agent_data.items())
        ]

    async def _runs_over_time(self, cutoff: datetime) -> list[dict[str, Any]]:
        """Daily run count using Python grouping for SQLite compat."""
        result = await self.session.execute(
            select(TaskRun.created_at).where(TaskRun.created_at >= cutoff)
        )
        rows = result.all()

        day_counts: dict[str, int] = {}
        for (created_at,) in rows:
            if created_at:
                day = created_at.strftime("%Y-%m-%d")
                day_counts[day] = day_counts.get(day, 0) + 1

        return [{"date": date, "count": count} for date, count in sorted(day_counts.items())]

    async def _cost_stats(self, cutoff: datetime) -> dict[str, Any]:
        """Aggregate cost data from agent invocations."""
        result = await self.session.execute(
            select(
                AgentInvocation.agent_name,
                AgentInvocation.estimated_tokens_in,
                AgentInvocation.estimated_tokens_out,
                AgentInvocation.estimated_cost_usd,
                AgentInvocation.run_id,
            ).where(
                AgentInvocation.started_at >= cutoff,
                AgentInvocation.estimated_cost_usd.isnot(None),
            )
        )
        rows = result.all()

        total_cost = 0.0
        total_tokens_in = 0
        total_tokens_out = 0
        per_agent: dict[str, float] = {}
        per_run: dict[int, float] = {}

        for agent_name, tok_in, tok_out, cost, run_id in rows:
            total_cost += cost or 0
            total_tokens_in += tok_in or 0
            total_tokens_out += tok_out or 0
            per_agent[agent_name] = per_agent.get(agent_name, 0) + (cost or 0)
            per_run[run_id] = per_run.get(run_id, 0) + (cost or 0)

        avg_cost_per_run = total_cost / len(per_run) if per_run else 0.0

        return {
            "total_cost_usd": round(total_cost, 4),
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "avg_cost_per_run_usd": round(avg_cost_per_run, 4),
            "cost_by_agent": [
                {"agent_name": name, "cost_usd": round(cost, 4)}
                for name, cost in sorted(per_agent.items())
            ],
        }