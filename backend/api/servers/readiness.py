# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace readiness validation API endpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.readiness_repo import WorkspaceReadinessRepository
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas.readiness import WorkspaceReadinessOut
from backend.services.workspace.command_executor import executor_for_server
from backend.services.workspace.readiness_service import TTL_DAYS, WorkspaceReadinessService

router = APIRouter(tags=["workspace-readiness"])


@router.get(
    "/workspace-servers/{server_id}/readiness",
    response_model=list[WorkspaceReadinessOut],
)
async def list_server_readiness(server_id: int, db: AsyncSession = Depends(get_db)):
    """Get readiness status for all projects on a server."""
    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    repo = WorkspaceReadinessRepository(db)
    return await repo.get_for_server(server_id)


@router.get(
    "/workspace-servers/{server_id}/projects/{project_id}/readiness",
    response_model=WorkspaceReadinessOut,
)
async def get_readiness(server_id: int, project_id: str, db: AsyncSession = Depends(get_db)):
    """Get workspace readiness status for a specific project+server pair."""
    repo = WorkspaceReadinessRepository(db)
    row = await repo.get(project_id, server_id)
    if not row:
        raise HTTPException(404, "No readiness record found")
    return row


@router.post(
    "/workspace-servers/{server_id}/projects/{project_id}/validate",
    response_model=WorkspaceReadinessOut,
)
async def trigger_validation(server_id: int, project_id: str, db: AsyncSession = Depends(get_db)):
    """Manually trigger workspace readiness validation."""
    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    project_repo = ProjectConfigRepository(db)
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Resolve workspace path
    ws_cfg = project.workspace_config or {}
    workspace_path = project.workspace_path or project_id
    if not workspace_path.startswith("/"):
        root = server.workspace_root or "/home/workspace"
        workspace_path = f"{root}/{workspace_path}".rstrip("/")

    ssh = executor_for_server(server)
    worker_user = server.worker_user
    dev_commands = ws_cfg.get("dev_commands")

    svc = WorkspaceReadinessService(ssh, worker_user=worker_user)
    result = await svc.validate(workspace_path, dev_commands=dev_commands)

    now = datetime.now(UTC)
    readiness_repo = WorkspaceReadinessRepository(db)
    return await readiness_repo.upsert(
        project_id,
        server_id,
        {
            "validation_status": "passed" if result.passed else "failed",
            "validated_at": now,
            "expires_at": (now + timedelta(days=TTL_DAYS)) if result.passed else None,
            "check_results": [asdict(c) for c in result.checks],
            "validation_report": result.report_dict(),
        },
    )
