# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Server group CRUD and token/key deployment endpoints."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ServerGroup, WorkspaceServer
from backend.repositories.server_group_repo import ServerGroupRepository
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas.server_groups import (
    ServerGroupCreate,
    ServerGroupDetail,
    ServerGroupOut,
    ServerGroupServerInfo,
    ServerGroupSetToken,
    ServerGroupUpdate,
)
from backend.services.encryption import decrypt_value, encrypt_value
from backend.services.git import GitAccessService
from backend.services.workspace.command_executor import executor_for_server

logger = logging.getLogger("agentickode.server_groups")

router = APIRouter(tags=["server-groups"])


def _get_repos(
    db: AsyncSession = Depends(get_db),
) -> tuple[ServerGroupRepository, WorkspaceServerRepository]:
    return ServerGroupRepository(db), WorkspaceServerRepository(db)


def _group_to_out(group: ServerGroup, server_count: int) -> ServerGroupOut:
    return ServerGroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        git_provider_type=group.git_provider_type,
        has_git_token=group.git_token_encrypted is not None,
        server_count=server_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def _group_to_detail(group: ServerGroup) -> ServerGroupDetail:
    servers_info = [
        ServerGroupServerInfo(id=s.id, name=s.name, hostname=s.hostname, status=s.status)
        for s in (group.servers or [])
    ]
    return ServerGroupDetail(
        id=group.id,
        name=group.name,
        description=group.description,
        git_provider_type=group.git_provider_type,
        has_git_token=group.git_token_encrypted is not None,
        server_count=len(servers_info),
        created_at=group.created_at,
        updated_at=group.updated_at,
        servers=servers_info,
    )


@router.get("/server-groups", response_model=list[ServerGroupOut])
async def list_server_groups(
    db: AsyncSession = Depends(get_db),
):
    repo = ServerGroupRepository(db)
    groups = await repo.list_all()
    results = []
    for g in groups:
        count = await repo.get_server_count(g.id)
        results.append(_group_to_out(g, count))
    return results


@router.post("/server-groups", response_model=ServerGroupOut, status_code=201)
async def create_server_group(
    body: ServerGroupCreate,
    db: AsyncSession = Depends(get_db),
):
    repo = ServerGroupRepository(db)
    existing = await repo.get_by_name(body.name)
    if existing:
        raise HTTPException(409, f"Server group '{body.name}' already exists")
    group = ServerGroup(name=body.name, description=body.description)
    group = await repo.create(group)
    return _group_to_out(group, 0)


@router.get("/server-groups/{group_id}", response_model=ServerGroupDetail)
async def get_server_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    repo = ServerGroupRepository(db)
    group = await repo.get_by_id_with_servers(group_id)
    if not group:
        raise HTTPException(404, "Server group not found")
    return _group_to_detail(group)


@router.put("/server-groups/{group_id}", response_model=ServerGroupOut)
async def update_server_group(
    group_id: int,
    body: ServerGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    repo = ServerGroupRepository(db)
    group = await repo.get_by_id(group_id)
    if not group:
        raise HTTPException(404, "Server group not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != group.name:
        dup = await repo.get_by_name(data["name"])
        if dup:
            raise HTTPException(409, f"Server group '{data['name']}' already exists")
    group = await repo.update(group, data)
    count = await repo.get_server_count(group.id)
    return _group_to_out(group, count)


@router.delete("/server-groups/{group_id}", status_code=204)
async def delete_server_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    repo = ServerGroupRepository(db)
    group = await repo.get_by_id(group_id)
    if not group:
        raise HTTPException(404, "Server group not found")
    await repo.delete(group)


@router.post("/server-groups/{group_id}/set-token", response_model=ServerGroupOut)
async def set_group_token(
    group_id: int,
    body: ServerGroupSetToken,
    db: AsyncSession = Depends(get_db),
):
    """Encrypt and store a git token for the group."""
    repo = ServerGroupRepository(db)
    group = await repo.get_by_id(group_id)
    if not group:
        raise HTTPException(404, "Server group not found")
    encrypted = encrypt_value(body.git_token)
    group = await repo.update(
        group,
        {"git_token_encrypted": encrypted, "git_provider_type": body.git_provider_type},
    )
    count = await repo.get_server_count(group.id)
    return _group_to_out(group, count)


@router.post("/server-groups/{group_id}/deploy-token")
async def deploy_group_token(
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Deploy the stored git token to all servers in the group via SSH."""
    repo = ServerGroupRepository(db)
    group = await repo.get_by_id_with_servers(group_id)
    if not group:
        raise HTTPException(404, "Server group not found")
    if not group.git_token_encrypted:
        raise HTTPException(400, "No git token set for this group")

    token = decrypt_value(group.git_token_encrypted)
    provider = group.git_provider_type or "github"

    results: list[dict] = []
    for server in group.servers:
        try:
            ssh = executor_for_server(server)
            cmd = _build_git_credential_cmd(provider, token, server.worker_user)
            stdout, stderr, rc = await ssh.run_command(cmd, timeout=30)
            results.append(
                {
                    "server_id": server.id,
                    "name": server.name,
                    "success": rc == 0,
                    "error": stderr if rc != 0 else None,
                }
            )
        except Exception as exc:
            results.append(
                {"server_id": server.id, "name": server.name, "success": False, "error": str(exc)}
            )
    return {"results": results}


@router.post("/server-groups/{group_id}/deploy-ssh-key")
async def deploy_group_ssh_key(
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate SSH key on first server, copy public key to all others."""
    repo = ServerGroupRepository(db)
    group = await repo.get_by_id_with_servers(group_id)
    if not group:
        raise HTTPException(404, "Server group not found")
    if not group.servers:
        raise HTTPException(400, "No servers in this group")

    source = group.servers[0]
    ssh_source = executor_for_server(source)
    svc = GitAccessService(ssh_source)

    key_info = await svc.generate_key(source.name, force=False, copy_to_user=source.worker_user)
    if not key_info.public_key:
        raise HTTPException(500, "Failed to generate or read SSH key on source server")

    public_key = key_info.public_key
    results = [{"server_id": source.id, "name": source.name, "success": True, "error": None}]

    async def _deploy_to(server: WorkspaceServer) -> dict:
        try:
            ssh = executor_for_server(server)
            cmd = (
                f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                f"grep -qF '{public_key}' ~/.ssh/authorized_keys 2>/dev/null || "
                f"echo '{public_key}' >> ~/.ssh/authorized_keys && "
                f"chmod 600 ~/.ssh/authorized_keys"
            )
            _, stderr, rc = await ssh.run_command(cmd, timeout=15)
            if server.worker_user:
                worker_cmd = (
                    f'runuser -l {server.worker_user} -c "'
                    f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                    f"grep -qF '{public_key}' ~/.ssh/authorized_keys 2>/dev/null || "
                    f"echo '{public_key}' >> ~/.ssh/authorized_keys && "
                    f'chmod 600 ~/.ssh/authorized_keys"'
                )
                await ssh.run_command(worker_cmd, timeout=15)
            return {
                "server_id": server.id,
                "name": server.name,
                "success": rc == 0,
                "error": stderr if rc != 0 else None,
            }
        except Exception as exc:
            return {
                "server_id": server.id,
                "name": server.name,
                "success": False,
                "error": str(exc),
            }

    targets = [s for s in group.servers if s.id != source.id]
    if targets:
        deploy_results = await asyncio.gather(*[_deploy_to(s) for s in targets])
        results.extend(deploy_results)

    return {"public_key": public_key, "results": results}


@router.post("/server-groups/{group_id}/add-server/{server_id}")
async def add_server_to_group(
    group_id: int,
    server_id: int,
    db: AsyncSession = Depends(get_db),
):
    group_repo = ServerGroupRepository(db)
    server_repo = WorkspaceServerRepository(db)

    group = await group_repo.get_by_id(group_id)
    if not group:
        raise HTTPException(404, "Server group not found")
    server = await server_repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    await server_repo.update(server, {"server_group_id": group_id})
    return {"status": "ok"}


@router.delete("/server-groups/{group_id}/remove-server/{server_id}")
async def remove_server_from_group(
    group_id: int,
    server_id: int,
    db: AsyncSession = Depends(get_db),
):
    group_repo = ServerGroupRepository(db)
    server_repo = WorkspaceServerRepository(db)

    group = await group_repo.get_by_id(group_id)
    if not group:
        raise HTTPException(404, "Server group not found")
    server = await server_repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    if server.server_group_id != group_id:
        raise HTTPException(400, "Server is not in this group")

    await server_repo.update(server, {"server_group_id": None})
    return {"status": "ok"}


def _build_git_credential_cmd(provider: str, token: str, worker_user: str | None) -> str:
    """Build shell command to configure git credential store with the token."""
    host_map = {
        "github": "github.com",
        "gitea": "",  # user must configure
        "gitlab": "gitlab.com",
        "bitbucket": "bitbucket.org",
    }
    host = host_map.get(provider, provider)
    if not host:
        host = provider

    credential_line = f"https://oauth2:{token}@{host}"
    cmds = [
        "git config --global credential.helper store",
        f"echo '{credential_line}' >> ~/.git-credentials",
        "chmod 600 ~/.git-credentials",
    ]
    base = " && ".join(cmds)
    if worker_user:
        worker_cmds = " && ".join(
            [
                f"runuser -l {worker_user} -c 'git config --global credential.helper store'",
                f"runuser -l {worker_user} -c \"echo '{credential_line}' >> ~/.git-credentials\"",
                f"runuser -l {worker_user} -c 'chmod 600 ~/.git-credentials'",
            ]
        )
        return f"{base} && {worker_cmds}"
    return base
