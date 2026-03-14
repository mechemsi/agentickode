# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Task run CRUD and stats."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ProjectConfig, TaskRun
from backend.repositories.task_run_repo import TaskRunRepository
from backend.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    PaginatedRunsResponse,
    TaskRunDetail,
)

logger = logging.getLogger("agentickode.runs")
router = APIRouter(tags=["runs"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> TaskRunRepository:
    return TaskRunRepository(db)


@router.get("/runs", response_model=PaginatedRunsResponse)
async def list_runs(
    status: str | None = None,
    project_id: str | None = None,
    search: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|title|status)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repo: TaskRunRepository = Depends(_get_repo),
):
    items, total = await repo.list_runs(
        status=status,
        project_id=project_id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return PaginatedRunsResponse(items=items, total=total, offset=offset, limit=limit)


@router.post("/runs", response_model=CreateRunResponse, status_code=201)
async def create_run(req: CreateRunRequest, db: AsyncSession = Depends(get_db)):
    project = await db.get(ProjectConfig, req.project_id)
    if not project:
        raise HTTPException(404, f"Project {req.project_id} not found")

    ts = int(time.time())
    slug = project.project_slug or project.repo_name
    branch_name = f"agentickode/{slug}/{ts}"

    ws_server_id = req.workspace_server_id or project.workspace_server_id
    workspace_path = project.workspace_path or project.repo_name

    # Build task_source_meta upfront so we never mutate Column objects
    meta: dict = {"labels": req.labels}
    if req.agent_override:
        meta["agent_override"] = req.agent_override
    if req.phase_overrides:
        meta["phase_overrides"] = req.phase_overrides
    if ws_server_id is not None:
        meta["workspace_server_id"] = ws_server_id
    if req.issue_number is not None:
        meta["issue_number"] = req.issue_number
    if req.issue_url:
        meta["issue_url"] = req.issue_url
    if req.skip_schedule:
        meta["skip_schedule"] = True

    run = TaskRun(
        task_id=f"manual-{ts}",
        project_id=req.project_id,
        title=req.title,
        description=req.description,
        branch_name=branch_name,
        workspace_path=workspace_path,
        repo_owner=project.repo_owner,
        repo_name=project.repo_name,
        default_branch=project.default_branch,
        task_source="manual",
        git_provider=project.git_provider,
        task_source_meta=meta,
        run_type=req.run_type,
        status="pending",
        workflow_template_id=req.workflow_template_id,
        workspace_config=project.workspace_config,
    )

    db.add(run)
    await db.flush()
    await db.commit()
    await db.refresh(run)

    logger.info(f"Created manual run #{run.id} for project {req.project_id}")
    return CreateRunResponse(
        id=run.id,
        status=run.status,
        title=run.title,
        project_id=run.project_id,
        branch_name=run.branch_name,
    )


@router.get("/runs/{run_id}", response_model=TaskRunDetail)
async def get_run(run_id: int, repo: TaskRunRepository = Depends(_get_repo)):
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/stats")
async def get_stats(repo: TaskRunRepository = Depends(_get_repo)):
    return await repo.get_stats()
