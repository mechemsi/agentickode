# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Git connection CRUD + test endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.git_connection_repo import GitConnectionRepository
from backend.schemas.git_connections import (
    VALID_GIT_PROVIDERS,
    VALID_SCOPES,
    GitConnectionCreate,
    GitConnectionOut,
    GitConnectionTestResult,
    GitConnectionUpdate,
)
from backend.services.encryption import decrypt_value
from backend.services.http_client import get_http_client

router = APIRouter(tags=["git-connections"])
logger = logging.getLogger("agentickode.git_connections")


def _get_repo(db: AsyncSession = Depends(get_db)) -> GitConnectionRepository:
    return GitConnectionRepository(db)


def _validate_provider(provider: str) -> None:
    if provider not in VALID_GIT_PROVIDERS:
        raise HTTPException(
            400, f"Invalid provider. Must be one of: {', '.join(sorted(VALID_GIT_PROVIDERS))}"
        )


def _validate_scope(scope: str) -> None:
    if scope not in VALID_SCOPES:
        raise HTTPException(
            400, f"Invalid scope. Must be one of: {', '.join(sorted(VALID_SCOPES))}"
        )


def _to_out(conn) -> GitConnectionOut:
    return GitConnectionOut(
        id=conn.id,
        name=conn.name,
        provider=conn.provider,
        base_url=conn.base_url,
        scope=conn.scope,
        workspace_server_id=conn.workspace_server_id,
        project_id=conn.project_id,
        is_default=conn.is_default,
        has_token=bool(conn.token_enc),
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.get("/git-connections", response_model=list[GitConnectionOut])
async def list_connections(
    scope: str | None = None,
    workspace_server_id: int | None = None,
    project_id: str | None = None,
    repo: GitConnectionRepository = Depends(_get_repo),
):
    conns = await repo.list_all(
        scope=scope, workspace_server_id=workspace_server_id, project_id=project_id
    )
    return [_to_out(c) for c in conns]


@router.post("/git-connections", response_model=GitConnectionOut, status_code=201)
async def create_connection(
    body: GitConnectionCreate,
    repo: GitConnectionRepository = Depends(_get_repo),
):
    _validate_provider(body.provider)
    _validate_scope(body.scope)
    conn = await repo.create(body)
    return _to_out(conn)


@router.put("/git-connections/{connection_id}", response_model=GitConnectionOut)
async def update_connection(
    connection_id: int,
    body: GitConnectionUpdate,
    repo: GitConnectionRepository = Depends(_get_repo),
):
    conn = await repo.get_by_id(connection_id)
    if not conn:
        raise HTTPException(404, "Git connection not found")
    data = body.model_dump(exclude_unset=True)
    conn = await repo.update(conn, data)
    return _to_out(conn)


@router.delete("/git-connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: int,
    repo: GitConnectionRepository = Depends(_get_repo),
):
    conn = await repo.get_by_id(connection_id)
    if not conn:
        raise HTTPException(404, "Git connection not found")
    await repo.delete(conn)


@router.post(
    "/git-connections/{connection_id}/test",
    response_model=GitConnectionTestResult,
)
async def test_connection(
    connection_id: int,
    repo: GitConnectionRepository = Depends(_get_repo),
):
    conn = await repo.get_by_id(connection_id)
    if not conn:
        raise HTTPException(404, "Git connection not found")
    token = decrypt_value(conn.token_enc)
    client = get_http_client()
    return await _test_provider(conn.provider, token, conn.base_url, client)


async def _test_provider(
    provider: str, token: str, base_url: str | None, client
) -> GitConnectionTestResult:
    """Make a test API call to verify the token works."""
    try:
        if provider == "github":
            resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=15,
            )
        elif provider == "gitlab":
            url = (base_url.rstrip("/") if base_url else "https://gitlab.com") + "/api/v4/user"
            resp = await client.get(url, headers={"PRIVATE-TOKEN": token}, timeout=15)
        elif provider == "bitbucket":
            resp = await client.get(
                "https://api.bitbucket.org/2.0/user",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=15,
            )
        elif provider == "gitea":
            if not base_url:
                return GitConnectionTestResult(success=False, error="base_url required for Gitea")
            url = base_url.rstrip("/") + "/api/v1/user"
            resp = await client.get(url, headers={"Authorization": f"token {token}"}, timeout=15)
        else:
            return GitConnectionTestResult(success=False, error=f"Unknown provider: {provider}")

        if resp.status_code == 200:
            data = resp.json()
            username = data.get("login") or data.get("username") or data.get("display_name")
            return GitConnectionTestResult(success=True, username=username)
        return GitConnectionTestResult(
            success=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}"
        )
    except Exception as exc:
        logger.warning("Git connection test failed for %s: %s", provider, exc)
        return GitConnectionTestResult(success=False, error=str(exc))
