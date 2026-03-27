# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CRUD endpoints for project scheduled tasks."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.agents import ScheduledTask
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.scheduled_task_repo import ScheduledTaskRepository
from backend.schemas.scheduled_tasks import (
    ScheduledTaskCreate,
    ScheduledTaskOut,
    ScheduledTaskUpdate,
)
from backend.services.cron_parser import next_occurrence
from backend.services.run_factory import create_task_run

logger = logging.getLogger("agentickode.api.scheduled_tasks")
router = APIRouter(tags=["scheduled-tasks"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> ScheduledTaskRepository:
    return ScheduledTaskRepository(db)


def _get_project_repo(db: AsyncSession = Depends(get_db)) -> ProjectConfigRepository:
    return ProjectConfigRepository(db)


@router.get("/projects/{project_id}/scheduled-tasks", response_model=list[ScheduledTaskOut])
async def list_scheduled_tasks(
    project_id: str,
    repo: ScheduledTaskRepository = Depends(_get_repo),
):
    return await repo.list_by_project(project_id)


@router.post("/projects/{project_id}/scheduled-tasks", response_model=ScheduledTaskOut)
async def create_scheduled_task(
    project_id: str,
    body: ScheduledTaskCreate,
    db: AsyncSession = Depends(get_db),
    repo: ScheduledTaskRepository = Depends(_get_repo),
    project_repo: ProjectConfigRepository = Depends(_get_project_repo),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    now = datetime.now(UTC)
    task = ScheduledTask(
        project_id=project_id,
        name=body.name,
        schedule=body.schedule,
        task_description=body.task_description,
        enabled=body.enabled,
        next_run_at=next_occurrence(body.schedule, now) if body.enabled else None,
    )
    task = await repo.create(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.put("/scheduled-tasks/{task_id}", response_model=ScheduledTaskOut)
async def update_scheduled_task(
    task_id: int,
    body: ScheduledTaskUpdate,
    db: AsyncSession = Depends(get_db),
    repo: ScheduledTaskRepository = Depends(_get_repo),
):
    task = await repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "Scheduled task not found")

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(task, key, value)

    if "schedule" in updates or "enabled" in updates:
        if task.enabled:
            task.next_run_at = next_occurrence(task.schedule, datetime.now(UTC))
        else:
            task.next_run_at = None

    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/scheduled-tasks/{task_id}")
async def delete_scheduled_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    repo: ScheduledTaskRepository = Depends(_get_repo),
):
    task = await repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "Scheduled task not found")
    await repo.delete(task)
    await db.commit()
    return {"status": "deleted"}


@router.post("/scheduled-tasks/{task_id}/trigger")
async def trigger_scheduled_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    repo: ScheduledTaskRepository = Depends(_get_repo),
    project_repo: ProjectConfigRepository = Depends(_get_project_repo),
):
    """Manually trigger a scheduled task (create a run immediately)."""
    task = await repo.get_by_id(task_id)
    if not task:
        raise HTTPException(404, "Scheduled task not found")

    project = await project_repo.get_by_id(task.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    run_task_id = f"sched-{task.id}-{uuid.uuid4().hex[:8]}"
    run = create_task_run(
        task_id=run_task_id,
        project=project,
        title=f"[Scheduled] {task.name}",
        description=task.task_description,
        task_source="scheduled",
        task_source_meta={
            "scheduled_task_id": task.id,
            "schedule": task.schedule,
            "scheduled_task_name": task.name,
            "manual_trigger": True,
        },
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info("Manually triggered scheduled task %d → run #%d", task_id, run.id)
    return {"status": "triggered", "run_id": run.id}
