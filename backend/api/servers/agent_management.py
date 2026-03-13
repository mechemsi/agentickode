# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent management endpoints for workspace servers."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from backend.database import get_db
from backend.models import DiscoveredAgent
from backend.models.agents import AgentSettings
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import (
    AgentInstallRequest,
    AgentInstallResult,
    AgentInstallStatus,
    AgentManagementStatus,
    UserAgentStatus,
)
from backend.services.workspace.agent_install_service import AgentInstallService
from backend.services.workspace.ssh_service import SSHService
from backend.services.workspace.worker_user_service import WorkerUserService

logger = logging.getLogger("agentickode.agent_management")

router = APIRouter(tags=["agent-management"])


async def _load_agent_settings(db: AsyncSession) -> list[AgentSettings]:
    """Load all AgentSettings rows from DB."""
    result = await db.execute(select(AgentSettings))
    return list(result.scalars().all())


@router.get("/supported-agents")
async def list_supported_agents(db: AsyncSession = Depends(get_db)):
    """Return the list of all agents the platform can install."""
    settings = await _load_agent_settings(db)
    return [
        {
            "name": s.agent_name,
            "display_name": s.display_name,
            "description": s.description,
            "agent_type": s.agent_type or "cli_binary",
        }
        for s in settings
    ]


def _get_repo(db: AsyncSession = Depends(get_db)) -> WorkspaceServerRepository:
    return WorkspaceServerRepository(db)


@router.post(
    "/workspace-servers/{server_id}/agents/status",
    response_model=AgentManagementStatus,
)
async def get_agent_status(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
    db: AsyncSession = Depends(get_db),
):
    """Check install status of all supported agents (worker user only)."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    settings = await _load_agent_settings(db)
    ssh = SSHService.for_server(server)
    svc = AgentInstallService(ssh, agent_settings=settings)

    username = server.worker_user or "coder"
    try:
        worker_agents = await svc.check_all_agents(as_user=username)
    except Exception:
        worker_agents = await svc.check_all_agents()

    agent_statuses = [
        AgentInstallStatus(
            agent_name=a.agent_name,
            display_name=a.display_name,
            description=a.description,
            agent_type=a.agent_type,
            installed=a.installed,
            version=a.version,
            path=a.path,
        )
        for a in worker_agents
    ]

    # Persist discovered worker agents to DB so list counts stay in sync
    try:
        db_agents = [
            DiscoveredAgent(
                agent_name=a.agent_name,
                agent_type=a.agent_type,
                path=a.path,
                version=a.version,
                available=a.installed,
            )
            for a in worker_agents
            if a.installed
        ]
        await repo.replace_agents_for_context(server_id, "worker", db_agents)
    except Exception:
        logger.warning("Failed to persist agent status for server %s", server_id)

    by_user = [UserAgentStatus(user=username, agents=agent_statuses)]
    return AgentManagementStatus(agents=agent_statuses, by_user=by_user)


@router.post(
    "/workspace-servers/{server_id}/agents/install",
    response_model=AgentInstallResult,
)
async def install_agent(
    server_id: int,
    body: AgentInstallRequest,
    repo: WorkspaceServerRepository = Depends(_get_repo),
    db: AsyncSession = Depends(get_db),
):
    """Install an agent directly on the worker user."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    settings = await _load_agent_settings(db)
    ssh = SSHService.for_server(server)
    svc = AgentInstallService(ssh, agent_settings=settings)

    username = server.worker_user or "coder"

    # Step 1: Ensure worker user exists with config/credentials
    user_svc = WorkerUserService(ssh)
    user_info = await user_svc.setup(username)
    if not user_info.exists:
        return AgentInstallResult(
            success=False,
            agent_name=body.agent_name,
            error=f"Failed to create worker user '{username}': {user_info.error}",
        )

    # Step 2: Install agent as the worker user
    result = await svc.install_agent(body.agent_name, as_user=username)
    if not result.success:
        return AgentInstallResult(
            success=False,
            agent_name=result.agent_name,
            error=result.error,
            output=result.output,
        )

    return AgentInstallResult(
        success=True,
        agent_name=body.agent_name,
        message=f"{body.agent_name} installed for worker user '{username}'",
        output=result.output,
    )


@router.post("/workspace-servers/{server_id}/agents/install-stream")
async def install_agent_stream(
    server_id: int,
    body: AgentInstallRequest,
    repo: WorkspaceServerRepository = Depends(_get_repo),
    db: AsyncSession = Depends(get_db),
):
    """Stream agent installation progress via SSE."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    settings = await _load_agent_settings(db)
    ssh = SSHService.for_server(server)
    svc = AgentInstallService(ssh, agent_settings=settings)
    username = server.worker_user or "coder"

    # Ensure worker user exists
    user_svc = WorkerUserService(ssh)
    user_info = await user_svc.setup(username)

    async def event_generator():
        if not user_info.exists:
            msg = f"Failed to create worker user '{username}': {user_info.error}"
            yield f"data: {json.dumps({'type': 'error', 'line': msg})}\n\n"
            return

        async for line in svc.install_agent_stream(body.agent_name, as_user=username):
            yield f"data: {json.dumps({'type': 'output', 'line': line})}\n\n"

        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/workspace-servers/{server_id}/agents/install-worker",
    response_model=AgentInstallResult,
    deprecated=True,
)
async def install_agent_for_worker(
    server_id: int,
    body: AgentInstallRequest,
    repo: WorkspaceServerRepository = Depends(_get_repo),
    db: AsyncSession = Depends(get_db),
):
    """Deprecated: use /install which now does combined install+copy."""
    return await install_agent(server_id, body, repo, db)
