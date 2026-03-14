# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace server operational endpoints (test, setup log, retry, invocations)."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session, get_db
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import (
    AgentInvocationOut,
    RetrySetupRequest,
    SSHTestResult,
)
from backend.services.workspace.setup_service import ServerSetupService
from backend.services.workspace.ssh_service import SSHService

router = APIRouter(tags=["workspace-servers"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> WorkspaceServerRepository:
    return WorkspaceServerRepository(db)


@router.post("/workspace-servers/{server_id}/test", response_model=SSHTestResult)
async def test_workspace_server(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    ssh = SSHService.for_server(server)
    result = await ssh.test_connection()
    if result.success:
        await repo.update(
            server,
            {
                "status": "online",
                "last_seen_at": datetime.now(UTC),
                "error_message": None,
            },
        )
    else:
        await repo.update(server, {"status": "error", "error_message": result.error})
    return SSHTestResult(success=result.success, latency_ms=result.latency_ms, error=result.error)


@router.get("/workspace-servers/{server_id}/setup-log")
async def get_setup_log(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
) -> dict[str, Any]:
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    log: dict[str, Any] = server.setup_log or {}  # type: ignore[assignment]
    return log


@router.post("/workspace-servers/{server_id}/retry-setup")
async def retry_server_setup(
    server_id: int,
    body: RetrySetupRequest | None = None,
    repo: WorkspaceServerRepository = Depends(_get_repo),
) -> dict[str, str]:
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    setup_service = ServerSetupService(async_session)
    password = body.setup_password if body else None
    setup_service.kick_off_setup(server.id, setup_password=password)
    return {"status": "setup_retrying"}


@router.get(
    "/workspace-servers/{server_id}/invocations",
    response_model=list[AgentInvocationOut],
)
async def list_server_invocations(
    server_id: int,
    agent_name: str | None = None,
    phase_name: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    from backend.models import AgentInvocation

    q = select(AgentInvocation).where(AgentInvocation.workspace_server_id == server_id)
    if agent_name:
        q = q.where(AgentInvocation.agent_name == agent_name)
    if phase_name:
        q = q.where(AgentInvocation.phase_name == phase_name)
    if status:
        q = q.where(AgentInvocation.status == status)
    q = q.order_by(AgentInvocation.started_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()
