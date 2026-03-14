# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace server discovery and scanning endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import DiscoveredAgent, ProjectConfig
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import (
    DeployKeyRequest,
    ScanResult,
    SSHTestResult,
)
from backend.services.workspace.agent_discovery import AgentDiscoveryService
from backend.services.workspace.project_discovery import ProjectDiscoveryService
from backend.services.workspace.ssh_service import SSHService

router = APIRouter(tags=["workspace-servers"])


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
