# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for TaskRun database operations."""

from typing import ClassVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import AgentInvocation, TaskRun


class TaskRunRepository:
    """Encapsulates all TaskRun database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    _SORT_COLUMNS: ClassVar[dict] = {
        "created_at": TaskRun.created_at,
        "updated_at": TaskRun.updated_at,
        "title": TaskRun.title,
        "status": TaskRun.status,
    }

    async def list_runs(
        self,
        status: str | None = None,
        project_id: str | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TaskRun], int]:
        # Subquery: sum estimated_cost_usd per run
        cost_sq = (
            select(
                AgentInvocation.run_id,
                func.sum(AgentInvocation.estimated_cost_usd).label("total_cost_usd"),
            )
            .group_by(AgentInvocation.run_id)
            .subquery()
        )

        # Build base filters
        filters = []
        if status:
            filters.append(TaskRun.status == status)
        if project_id:
            filters.append(TaskRun.project_id == project_id)
        if search:
            pattern = f"%{search}%"
            filters.append(TaskRun.title.ilike(pattern) | TaskRun.description.ilike(pattern))

        # Count query
        count_q = select(func.count()).select_from(TaskRun)
        for f in filters:
            count_q = count_q.where(f)
        total = (await self._session.execute(count_q)).scalar() or 0

        # Sort
        sort_col = self._SORT_COLUMNS.get(sort_by, TaskRun.created_at)
        order = sort_col.asc() if sort_order == "asc" else sort_col.desc()

        q = (
            select(TaskRun, cost_sq.c.total_cost_usd)
            .outerjoin(cost_sq, TaskRun.id == cost_sq.c.run_id)
            .order_by(order)
            .limit(limit)
            .offset(offset)
        )
        for f in filters:
            q = q.where(f)

        result = await self._session.execute(q)
        runs = []
        for row in result.all():
            run = row[0]
            run.total_cost_usd = row[1]
            runs.append(run)
        return runs, total

    async def get_by_id(self, run_id: int) -> TaskRun | None:
        result = await self._session.execute(
            select(TaskRun)
            .where(TaskRun.id == run_id)
            .options(selectinload(TaskRun.phase_executions))
        )
        return result.scalar_one_or_none()

    async def get_stats(self) -> dict[str, int]:
        result = await self._session.execute(
            select(TaskRun.status, func.count()).group_by(TaskRun.status)
        )
        counts = {row[0]: row[1] for row in result.all()}
        total = sum(counts.values())
        return {
            "total_runs": total,
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "awaiting_approval": counts.get("awaiting_approval", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
        }

    async def get_pending(self, limit: int = 1) -> list[TaskRun]:
        result = await self._session.execute(
            select(TaskRun)
            .where(TaskRun.status == "pending")
            .order_by(TaskRun.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_decided(self) -> list[TaskRun]:
        result = await self._session.execute(
            select(TaskRun).where(
                TaskRun.status == "awaiting_approval",
                TaskRun.approved.isnot(None),
            )
        )
        return list(result.scalars().all())

    async def get_timed_out(self, cutoff) -> list[TaskRun]:
        result = await self._session.execute(
            select(TaskRun).where(
                TaskRun.status == "awaiting_approval",
                TaskRun.approved.is_(None),
                TaskRun.approval_requested_at < cutoff,
            )
        )
        return list(result.scalars().all())

    async def get_active_count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(TaskRun).where(TaskRun.status == "running")
        )
        return result.scalar() or 0

    def add(self, run: TaskRun) -> None:
        self._session.add(run)

    async def commit(self) -> None:
        await self._session.commit()

    async def refresh(self, run: TaskRun) -> None:
        await self._session.refresh(run)
