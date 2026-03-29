# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CRUD + trigger endpoints for platform crons (scheduled prompts to agent sessions)."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.platform_crons import PlatformCron
from backend.repositories.platform_cron_repo import PlatformCronRepository
from backend.services.cron_parser import next_occurrence

logger = logging.getLogger("agentickode.api.platform_crons")
router = APIRouter(tags=["platform-crons"])


class PlatformCronCreate(BaseModel):
    name: str
    description: str | None = None
    schedule: str  # 5-field cron
    prompt: str
    session_id: str | None = None
    agent_name: str = "claude"
    enabled: bool = True


class PlatformCronUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    schedule: str | None = None
    prompt: str | None = None
    session_id: str | None = None
    agent_name: str | None = None
    enabled: bool | None = None


class PlatformCronOut(BaseModel):
    id: int
    name: str
    description: str | None
    schedule: str
    prompt: str
    session_id: str | None
    agent_name: str
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_result: str | None
    run_count: int
    execution_log: list
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/platform-crons", response_model=list[PlatformCronOut])
async def list_platform_crons(db: AsyncSession = Depends(get_db)):
    repo = PlatformCronRepository(db)
    return await repo.list_all()


@router.post("/platform-crons", response_model=PlatformCronOut)
async def create_platform_cron(
    body: PlatformCronCreate,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(UTC)
    next_run = next_occurrence(body.schedule, now) if body.enabled else None

    cron = PlatformCron(
        name=body.name,
        description=body.description,
        schedule=body.schedule,
        prompt=body.prompt,
        session_id=body.session_id,
        agent_name=body.agent_name,
        enabled=body.enabled,
        next_run_at=next_run,
    )
    repo = PlatformCronRepository(db)
    await repo.create(cron)
    await db.commit()
    await db.refresh(cron)
    return cron


@router.put("/platform-crons/{cron_id}", response_model=PlatformCronOut)
async def update_platform_cron(
    cron_id: int,
    body: PlatformCronUpdate,
    db: AsyncSession = Depends(get_db),
):
    repo = PlatformCronRepository(db)
    cron = await repo.get_by_id(cron_id)
    if not cron:
        raise HTTPException(404, "Platform cron not found")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(cron, key, value)

    if cron.enabled:
        cron.next_run_at = next_occurrence(cron.schedule, datetime.now(UTC))
    else:
        cron.next_run_at = None

    await db.commit()
    await db.refresh(cron)
    return cron


@router.delete("/platform-crons/{cron_id}")
async def delete_platform_cron(
    cron_id: int,
    db: AsyncSession = Depends(get_db),
):
    repo = PlatformCronRepository(db)
    cron = await repo.get_by_id(cron_id)
    if not cron:
        raise HTTPException(404, "Platform cron not found")
    await repo.delete(cron)
    await db.commit()
    return {"status": "deleted"}


@router.post("/platform-crons/{cron_id}/trigger")
async def trigger_platform_cron(
    cron_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a platform cron (send prompt to session now)."""
    from backend.services.platform_cron_executor import PlatformCronExecutor

    repo = PlatformCronRepository(db)
    cron = await repo.get_by_id(cron_id)
    if not cron:
        raise HTTPException(404, "Platform cron not found")

    executor = PlatformCronExecutor(db)
    result = await executor.execute_cron(cron)
    await db.commit()
    return {"status": result}
