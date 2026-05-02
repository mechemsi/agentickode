# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Shared deduplication helper for issue pollers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun


async def existing_task_ids(
    session: AsyncSession, project_id: str, task_source: str, task_ids: list[str]
) -> set[str]:
    """Return the subset of task_ids that already have a TaskRun for this project/source."""
    if not task_ids:
        return set()
    result = await session.execute(
        select(TaskRun.task_id).where(
            TaskRun.project_id == project_id,
            TaskRun.task_source == task_source,
            TaskRun.task_id.in_(task_ids),
        )
    )
    return {str(row) for row in result.scalars().all()}
