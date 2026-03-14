# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace server CRUD endpoints."""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session, get_db
from backend.models import WorkspaceServer
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import (
    DiscoveredAgentOut,
    WorkspaceServerCreate,
    WorkspaceServerDetail,
    WorkspaceServerOut,
    WorkspaceServerUpdate,
)
from backend.services.workspace.setup_service import ServerSetupService
from backend.services.workspace.ssh_service import SSHService

router = APIRouter(tags=["workspace-servers"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> WorkspaceServerRepository:
    return WorkspaceServerRepository(db)


def _server_to_out(server: WorkspaceServer, agent_count: int, project_count: int):
    return WorkspaceServerOut(
        id=server.id,
        name=server.name,
        hostname=server.hostname,
        port=server.port,
        username=server.username,
        ssh_key_path=server.ssh_key_path,
        workspace_root=server.workspace_root,
        status=server.status,
        last_seen_at=server.last_seen_at,
        error_message=server.error_message,
        worker_user=server.worker_user,
        worker_user_status=server.worker_user_status,
        setup_log=server.setup_log,
        agent_count=agent_count,
        project_count=project_count,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


async def _ping_server(server: WorkspaceServer) -> tuple[int, bool, str | None]:
    """Quick SSH ping. Returns (server_id, reachable, error)."""
    if server.status in ("setting_up",):
        return int(server.id), server.status == "online", None
    try:
        ssh = SSHService.for_server(server)
        result = await asyncio.wait_for(ssh.test_connection(), timeout=5)
        return int(server.id), result.success, result.error
    except Exception as exc:
        return int(server.id), False, str(exc)


def _server_to_detail(server: WorkspaceServer, ac: int, pc: int) -> WorkspaceServerDetail:
    return WorkspaceServerDetail(
        id=server.id,
        name=server.name,
        hostname=server.hostname,
        port=server.port,
        username=server.username,
        ssh_key_path=server.ssh_key_path,
        workspace_root=server.workspace_root,
        status=server.status,
        last_seen_at=server.last_seen_at,
        error_message=server.error_message,
        worker_user=server.worker_user,
        worker_user_status=server.worker_user_status,
        setup_log=server.setup_log,
        agent_count=ac,
        project_count=pc,
        created_at=server.created_at,
        updated_at=server.updated_at,
        agents=[
            DiscoveredAgentOut.model_validate(a)
            for a in server.agents
            if a.user_context == "worker"
        ],
    )


@router.get("/workspace-servers", response_model=list[WorkspaceServerOut])
async def list_workspace_servers(
    repo: WorkspaceServerRepository = Depends(_get_repo),
    check: bool = Query(False, description="Ping servers to verify online status"),
):
    servers = await repo.list_all()

    if check and servers:
        # Ping all servers concurrently (each with 5s timeout)
        ping_results = await asyncio.gather(
            *[_ping_server(s) for s in servers], return_exceptions=True
        )
        # Build lookup: server_id -> (reachable, error)
        status_map: dict[int, tuple[bool, str | None]] = {}
        for r in ping_results:
            if isinstance(r, tuple):
                sid, reachable, err = r
                status_map[sid] = (reachable, err)

        # Update statuses sequentially (safe for single session)
        now = datetime.now(UTC)
        for s in servers:
            ping = status_map.get(s.id)
            if ping is None:
                continue
            reachable, err = ping
            if reachable:
                if s.status != "online":
                    await repo.update(
                        s, {"status": "online", "last_seen_at": now, "error_message": None}
                    )
                else:
                    await repo.update(s, {"last_seen_at": now})
            elif s.status == "online":
                await repo.update(s, {"status": "offline", "error_message": err})

        # Re-fetch after status updates
        servers = await repo.list_all()

    results = []
    for s in servers:
        ac = await repo.get_agent_count(s.id)
        pc = await repo.get_project_count(s.id)
        results.append(_server_to_out(s, ac, pc))
    return results


@router.post("/workspace-servers", response_model=WorkspaceServerDetail, status_code=201)
async def create_workspace_server(
    body: WorkspaceServerCreate,
    db: AsyncSession = Depends(get_db),
):
    repo = WorkspaceServerRepository(db)

    data = body.model_dump(exclude={"setup_password"})
    if not data.get("workspace_root"):
        data["workspace_root"] = "/workspaces"  # Default until setup overwrites
    data["status"] = "setting_up"
    server = WorkspaceServer(**data)
    server = await repo.create(server)

    # Kick off async setup in background
    setup_service = ServerSetupService(async_session)
    setup_service.kick_off_setup(server.id, setup_password=body.setup_password)

    reloaded = await repo.get_by_id_with_agents(server.id)
    assert reloaded is not None
    ac = await repo.get_agent_count(reloaded.id)
    pc = await repo.get_project_count(reloaded.id)
    return _server_to_detail(reloaded, ac, pc)


@router.get("/workspace-servers/{server_id}", response_model=WorkspaceServerDetail)
async def get_workspace_server(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    server = await repo.get_by_id_with_agents(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    ac = await repo.get_agent_count(server.id)
    pc = await repo.get_project_count(server.id)
    return _server_to_detail(server, ac, pc)


@router.put("/workspace-servers/{server_id}", response_model=WorkspaceServerOut)
async def update_workspace_server(
    server_id: int,
    body: WorkspaceServerUpdate,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    server = await repo.update(server, body.model_dump(exclude_unset=True))
    ac = await repo.get_agent_count(server.id)
    pc = await repo.get_project_count(server.id)
    return _server_to_out(server, ac, pc)


@router.delete("/workspace-servers/{server_id}", status_code=204)
async def delete_workspace_server(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    await repo.delete(server)
