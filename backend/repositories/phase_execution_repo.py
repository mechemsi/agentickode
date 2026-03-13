# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for PhaseExecution database operations."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PhaseExecution


class PhaseExecutionRepository:
    """Encapsulates all PhaseExecution database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_for_run(
        self, run_id: int, phases_config: list[dict[str, Any]]
    ) -> list[PhaseExecution]:
        """Bulk-create PhaseExecution rows from resolved template phases."""
        executions = []
        for idx, phase_cfg in enumerate(phases_config):
            pe = PhaseExecution(
                run_id=run_id,
                phase_name=phase_cfg["phase_name"],
                order_index=idx,
                trigger_mode=phase_cfg.get("trigger_mode", "auto"),
                max_retries=phase_cfg.get("max_retries", 3),
                agent_override=phase_cfg.get("agent_override"),
                notify_source=phase_cfg.get("notify_source", False),
                phase_config=phase_cfg,
            )
            self._session.add(pe)
            executions.append(pe)
        await self._session.flush()
        return executions

    async def get_by_run(self, run_id: int) -> list[PhaseExecution]:
        """List all phases for a run, ordered by order_index."""
        result = await self._session.execute(
            select(PhaseExecution)
            .where(PhaseExecution.run_id == run_id)
            .order_by(PhaseExecution.order_index)
        )
        return list(result.scalars().all())

    async def get_by_run_and_phase(self, run_id: int, phase_name: str) -> PhaseExecution | None:
        """Look up a single phase execution by run and phase name."""
        result = await self._session.execute(
            select(PhaseExecution).where(
                PhaseExecution.run_id == run_id,
                PhaseExecution.phase_name == phase_name,
            )
        )
        return result.scalar_one_or_none()

    async def get_next_pending(self, run_id: int) -> PhaseExecution | None:
        """Return the first pending phase for a run."""
        result = await self._session.execute(
            select(PhaseExecution)
            .where(
                PhaseExecution.run_id == run_id,
                PhaseExecution.status == "pending",
            )
            .order_by(PhaseExecution.order_index)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        phase_exec: PhaseExecution,
        status: str,
        **kwargs: Any,
    ) -> None:
        """Transition a phase execution to a new status."""
        phase_exec.status = status
        for key, value in kwargs.items():
            setattr(phase_exec, key, value)
        if status == "running" and phase_exec.started_at is None:
            phase_exec.started_at = datetime.now(UTC)
        if status in ("completed", "failed", "skipped"):
            phase_exec.completed_at = datetime.now(UTC)
        await self._session.flush()
