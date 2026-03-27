# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for ScheduledTask database operations."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agents import ScheduledTask


class ScheduledTaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_by_project(self, project_id: str) -> list[ScheduledTask]:
        result = await self._session.execute(
            select(ScheduledTask)
            .where(ScheduledTask.project_id == project_id)
            .order_by(ScheduledTask.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, task_id: int) -> ScheduledTask | None:
        result = await self._session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_due(self, now: datetime | None = None) -> list[ScheduledTask]:
        """Return all enabled tasks whose next_run_at <= now."""
        now = now or datetime.now(UTC)
        result = await self._session.execute(
            select(ScheduledTask)
            .where(
                ScheduledTask.enabled.is_(True),
                ScheduledTask.next_run_at.isnot(None),
                ScheduledTask.next_run_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def create(self, task: ScheduledTask) -> ScheduledTask:
        self._session.add(task)
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def mark_executed(self, task: ScheduledTask, next_run_at: datetime) -> None:
        """Update last_run_at and compute next_run_at after dispatch."""
        await self._session.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id == task.id)
            .values(
                last_run_at=datetime.now(UTC),
                next_run_at=next_run_at,
            )
        )

    async def delete(self, task: ScheduledTask) -> None:
        await self._session.delete(task)
