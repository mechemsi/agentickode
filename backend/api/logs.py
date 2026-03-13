# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Task run log retrieval."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import TaskLog
from backend.schemas import TaskLogOut

router = APIRouter(tags=["logs"])


@router.get("/runs/{run_id}/logs", response_model=list[TaskLogOut])
async def get_run_logs(
    run_id: int,
    limit: int = Query(200, ge=1, le=1000),
    after_id: int | None = None,
    level: str | None = None,
    phase: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(TaskLog).where(TaskLog.run_id == run_id).order_by(TaskLog.id).limit(limit)
    if after_id:
        q = q.where(TaskLog.id > after_id)
    if level:
        q = q.where(TaskLog.level == level)
    if phase:
        q = q.where(TaskLog.phase == phase)
    result = await db.execute(q)
    return result.scalars().all()
