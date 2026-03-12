# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Worker user management endpoints for workspace servers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import (
    WorkerUserPasswordRequest,
    WorkerUserPasswordResult,
    WorkerUserSetupRequest,
    WorkerUserSetupResult,
    WorkerUserStatus,
)
from backend.services.workspace.ssh_service import SSHService
from backend.services.workspace.worker_user_service import WorkerUserService

router = APIRouter(tags=["worker-user"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> WorkspaceServerRepository:
    return WorkspaceServerRepository(db)


@router.post(
    "/workspace-servers/{server_id}/worker-user/setup",
    response_model=WorkerUserSetupResult,
)
async def setup_worker_user(
    server_id: int,
    body: WorkerUserSetupRequest | None = None,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Create a non-root worker user and copy CLI binaries."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    username = body.username if body else "coder"

    await repo.update(
        server,
        {"worker_user": username, "worker_user_status": "pending", "worker_user_error": None},
    )

    ssh = SSHService.for_server(server)
    svc = WorkerUserService(ssh)
    info = await svc.setup(username)

    if info.error:
        await repo.update(server, {"worker_user_status": "error", "worker_user_error": info.error})
        return WorkerUserSetupResult(
            success=False,
            username=username,
            status="error",
            error=info.error,
        )

    await repo.update(server, {"worker_user_status": "ready", "worker_user_error": None})
    return WorkerUserSetupResult(
        success=True,
        username=username,
        status="ready",
        agents=info.agents,
    )


@router.post(
    "/workspace-servers/{server_id}/worker-user/status",
    response_model=WorkerUserStatus,
)
async def check_worker_user(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Check current worker user configuration and agent availability."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    if not server.worker_user:
        return WorkerUserStatus(username=None, status=None)

    ssh = SSHService.for_server(server)
    svc = WorkerUserService(ssh)
    info = await svc.check_status(server.worker_user)

    status = "ready" if info.exists and info.agents else "error"
    error = None if info.exists else f"User {server.worker_user} does not exist"

    await repo.update(server, {"worker_user_status": status, "worker_user_error": error})
    return WorkerUserStatus(
        username=server.worker_user,
        status=status,
        error=error,
        agents=info.agents,
    )


@router.post(
    "/workspace-servers/{server_id}/worker-user/sync",
    response_model=WorkerUserSetupResult,
)
async def sync_worker_user(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Re-sync binaries after new agent installs."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    if not server.worker_user:
        raise HTTPException(400, "No worker user configured")

    ssh = SSHService.for_server(server)
    svc = WorkerUserService(ssh)
    info = await svc.sync_agents(server.worker_user)

    if info.error:
        await repo.update(server, {"worker_user_status": "error", "worker_user_error": info.error})
        return WorkerUserSetupResult(
            success=False,
            username=server.worker_user,
            status="error",
            error=info.error,
        )

    await repo.update(server, {"worker_user_status": "ready", "worker_user_error": None})
    return WorkerUserSetupResult(
        success=True,
        username=server.worker_user,
        status="ready",
        agents=info.agents,
    )


@router.post(
    "/workspace-servers/{server_id}/worker-user/set-password",
    response_model=WorkerUserPasswordResult,
)
async def set_worker_user_password(
    server_id: int,
    body: WorkerUserPasswordRequest,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Set the OS password for the worker user."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    if not server.worker_user:
        raise HTTPException(400, "No worker user configured")

    ssh = SSHService.for_server(server)
    svc = WorkerUserService(ssh)
    info = await svc.set_password(server.worker_user, body.password)

    if info.error:
        return WorkerUserPasswordResult(success=False, error=info.error)

    await repo.update(server, {"worker_user_password": body.password})
    return WorkerUserPasswordResult(success=True)


@router.delete("/workspace-servers/{server_id}/worker-user", status_code=204)
async def delete_worker_user(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Clear worker user configuration (does not remove OS user)."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    await repo.update(
        server,
        {
            "worker_user": None,
            "worker_user_status": None,
            "worker_user_error": None,
            "worker_user_password": None,
        },
    )