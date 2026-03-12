# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace server CRUD with SSH test and agent/project discovery."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session, get_db
from backend.models import DiscoveredAgent, ProjectConfig, WorkspaceServer
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import (
    AgentInvocationOut,
    DeployKeyRequest,
    DiscoveredAgentOut,
    RetrySetupRequest,
    ScanResult,
    SSHTestResult,
    WorkspaceServerCreate,
    WorkspaceServerDetail,
    WorkspaceServerOut,
    WorkspaceServerUpdate,
)
from backend.services.workspace.agent_discovery import AgentDiscoveryService
from backend.services.workspace.project_discovery import ProjectDiscoveryService
from backend.services.workspace.setup_service import ServerSetupService
from backend.services.workspace.ssh_service import SSHService

router = APIRouter(tags=["workspace-servers"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> WorkspaceServerRepository:
    return WorkspaceServerRepository(db)


def _get_project_repo(db: AsyncSession = Depends(get_db)) -> ProjectConfigRepository:
    return ProjectConfigRepository(db)


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


@router.post("/workspace-servers/{server_id}/deploy-key", response_model=SSHTestResult)
async def deploy_key_to_server(
    server_id: int,
    body: DeployKeyRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = WorkspaceServerRepository(db)
    project_repo = ProjectConfigRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    ssh = SSHService.for_server(server)
    result = await ssh.deploy_key(body.password)

    if result.success:
        server = await repo.update(
            server,
            {
                "status": "online",
                "last_seen_at": datetime.now(UTC),
                "error_message": None,
            },
        )

        # Run agent/project discovery (both users)
        discovery = AgentDiscoveryService(ssh)
        admin_infos = await discovery.discover_all()
        admin_agents = [
            DiscoveredAgent(
                agent_name=a.agent_name,
                agent_type=a.agent_type,
                path=a.path,
                version=a.version,
                available=a.available,
                metadata_=a.metadata,
            )
            for a in admin_infos
        ]
        await repo.replace_agents_for_context(server.id, "admin", admin_agents)

        wk_user = server.worker_user or "coder"
        try:
            worker_infos = await discovery.discover_all(as_user=wk_user)
        except Exception:
            worker_infos = []
        worker_agents = [
            DiscoveredAgent(
                agent_name=a.agent_name,
                agent_type=a.agent_type,
                path=a.path,
                version=a.version,
                available=a.available,
                metadata_=a.metadata,
            )
            for a in worker_infos
        ]
        await repo.replace_agents_for_context(server.id, "worker", worker_agents)

        proj_discovery = ProjectDiscoveryService(ssh)
        discovered = await proj_discovery.scan_workspace(server.workspace_root)
        for dp in discovered:
            existing = await project_repo.find_by_repo(dp.owner, dp.name)
            if existing is None:
                proj = ProjectConfig(
                    project_id=f"{dp.owner}/{dp.name}",
                    project_slug=dp.name,
                    repo_owner=dp.owner,
                    repo_name=dp.name,
                    git_provider=dp.git_provider,
                    workspace_server_id=server.id,
                    workspace_path=dp.path,
                )
                await project_repo.create(proj)
            else:
                await project_repo.update(
                    existing,
                    {"workspace_path": dp.path, "workspace_server_id": server.id},
                )
    else:
        await repo.update(server, {"status": "error", "error_message": result.error})

    return SSHTestResult(
        success=result.success,
        latency_ms=result.latency_ms,
        error=result.error,
    )


@router.post("/workspace-servers/{server_id}/scan", response_model=ScanResult)
async def scan_workspace_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
):
    repo = WorkspaceServerRepository(db)
    project_repo = ProjectConfigRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    ssh = SSHService.for_server(server)

    # Verify SSH connectivity first
    test = await ssh.test_connection()
    if not test.success:
        await repo.update(server, {"status": "error", "error_message": test.error})
        raise HTTPException(502, f"SSH connection failed: {test.error}")

    # Discover agents for both admin and worker contexts
    try:
        discovery = AgentDiscoveryService(ssh)
        admin_infos = await discovery.discover_all()
    except Exception as exc:
        await repo.update(server, {"status": "error", "error_message": str(exc)})
        raise HTTPException(502, f"Agent discovery failed: {exc}") from exc
    admin_agents = [
        DiscoveredAgent(
            agent_name=a.agent_name,
            agent_type=a.agent_type,
            path=a.path,
            version=a.version,
            available=a.available,
            metadata_=a.metadata,
        )
        for a in admin_infos
    ]
    await repo.replace_agents_for_context(server.id, "admin", admin_agents)

    username = server.worker_user or "coder"
    try:
        worker_infos = await discovery.discover_all(as_user=username)
    except Exception:
        worker_infos = []
    worker_agents = [
        DiscoveredAgent(
            agent_name=a.agent_name,
            agent_type=a.agent_type,
            path=a.path,
            version=a.version,
            available=a.available,
            metadata_=a.metadata,
        )
        for a in worker_infos
    ]
    await repo.replace_agents_for_context(server.id, "worker", worker_agents)

    # Discover projects
    try:
        proj_discovery = ProjectDiscoveryService(ssh)
        discovered = await proj_discovery.scan_workspace(server.workspace_root)
    except Exception as exc:
        await repo.update(server, {"status": "error", "error_message": str(exc)})
        raise HTTPException(502, f"Project discovery failed: {exc}") from exc
    imported = 0
    for dp in discovered:
        existing = await project_repo.find_by_repo(dp.owner, dp.name)
        if existing is None:
            proj = ProjectConfig(
                project_id=f"{dp.owner}/{dp.name}",
                project_slug=dp.name,
                repo_owner=dp.owner,
                repo_name=dp.name,
                git_provider=dp.git_provider,
                workspace_server_id=server.id,
                workspace_path=dp.path,
            )
            await project_repo.create(proj)
            imported += 1
        else:
            await project_repo.update(
                existing,
                {"workspace_path": dp.path, "workspace_server_id": server.id},
            )

    await repo.update(
        server,
        {"status": "online", "last_seen_at": datetime.now(UTC)},
    )

    return ScanResult(
        agents_found=len(worker_agents),
        projects_found=len(discovered),
        projects_imported=imported,
    )


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


@router.get("/workspace-servers/{server_id}/invocations", response_model=list[AgentInvocationOut])
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