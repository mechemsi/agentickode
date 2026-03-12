# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Git provider SSH connectivity endpoints for workspace servers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import (
    GitAccessCheckRequest,
    GitAccessGenerateKeyRequest,
    GitAccessStatus,
    GitProviderStatus,
    UserGitAccessStatus,
)
from backend.services.git import GitAccessService
from backend.services.workspace.ssh_service import SSHService

router = APIRouter(tags=["git-access"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> WorkspaceServerRepository:
    return WorkspaceServerRepository(db)


@router.post(
    "/workspace-servers/{server_id}/git-access/check",
    response_model=GitAccessStatus,
)
async def check_git_access(
    server_id: int,
    body: GitAccessCheckRequest | None = None,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Check SSH key and git provider connectivity on a workspace server."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    ssh = SSHService.for_server(server)
    svc = GitAccessService(ssh)

    custom: list[tuple[str, str]] | None = None
    if body and body.custom_hosts:
        custom = [(h, h) for h in body.custom_hosts]

    key_info, providers = await svc.check_all(custom_hosts=custom)

    main_provider_statuses = [
        GitProviderStatus(
            host=p.host,
            name=p.name,
            connected=p.connected,
            username=p.username,
            error=p.error,
        )
        for p in providers
    ]

    by_user = [
        UserGitAccessStatus(
            user=server.username,
            has_key=key_info.has_key,
            public_key=key_info.public_key,
            key_type=key_info.key_type,
            providers=main_provider_statuses,
        )
    ]

    # Check worker user if configured (via runuser, not separate SSH)
    if server.worker_user:
        try:
            wk_key, wk_providers = await svc.check_all(
                custom_hosts=custom, as_user=server.worker_user
            )
            by_user.append(
                UserGitAccessStatus(
                    user=server.worker_user,
                    has_key=wk_key.has_key,
                    public_key=wk_key.public_key,
                    key_type=wk_key.key_type,
                    providers=[
                        GitProviderStatus(
                            host=p.host,
                            name=p.name,
                            connected=p.connected,
                            username=p.username,
                            error=p.error,
                        )
                        for p in wk_providers
                    ],
                )
            )
        except Exception:
            pass  # Worker user may not exist yet

    return GitAccessStatus(
        has_key=key_info.has_key,
        public_key=key_info.public_key,
        key_type=key_info.key_type,
        providers=main_provider_statuses,
        by_user=by_user,
    )


@router.post(
    "/workspace-servers/{server_id}/git-access/sync-keys",
    response_model=GitAccessStatus,
)
async def sync_git_keys(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Copy root SSH keys to the worker user so both have the same git access."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    if not server.worker_user:
        raise HTTPException(400, "No worker user configured on this server")

    ssh = SSHService.for_server(server)
    svc = GitAccessService(ssh)

    root_key = await svc.get_public_key()
    if not root_key.has_key:
        raise HTTPException(400, "No SSH key found for root user — generate one first")

    await svc._copy_key_to_user(server.worker_user)

    # Return full status including worker user
    return await check_git_access(server_id, repo=repo)


@router.post(
    "/workspace-servers/{server_id}/git-access/generate-key",
    response_model=GitAccessStatus,
)
async def generate_git_key(
    server_id: int,
    body: GitAccessGenerateKeyRequest | None = None,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Generate an SSH key on the workspace server and return access status."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    ssh = SSHService.for_server(server)
    svc = GitAccessService(ssh)

    force = body.force if body else False
    key_info = await svc.generate_key(server.name, force=force, copy_to_user=server.worker_user)

    return GitAccessStatus(
        has_key=key_info.has_key,
        public_key=key_info.public_key,
        key_type=key_info.key_type,
    )