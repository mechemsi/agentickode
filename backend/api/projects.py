# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Project config CRUD."""

import contextlib
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models import ProjectConfig
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import ProjectConfigCreate, ProjectConfigOut, ProjectConfigUpdate
from backend.schemas.projects import (
    GitUrlParseRequest,
    GitUrlParseResponse,
    TestConnectionRequest,
    TestConnectionResponse,
)
from backend.services.encryption import encrypt_value
from backend.services.git.repo_info import get_default_branch, get_default_branch_via_ssh
from backend.services.git.url_parser import parse_git_url
from backend.services.http_client import get_http_client
from backend.services.workspace.ssh_service import SSHService

router = APIRouter(tags=["projects"])

_PROVIDER_HOSTS = {
    "github": "github.com",
    "gitlab": "gitlab.com",
    "bitbucket": "bitbucket.org",
}


def _provider_host(provider: str) -> str:
    """Return the SSH hostname for a known git provider."""
    if provider in _PROVIDER_HOSTS:
        return _PROVIDER_HOSTS[provider]
    # For gitea and other self-hosted providers, derive hostname from configured URL
    parsed = urlparse(settings.gitea_url)
    return parsed.hostname or "gitea.local"


def _project_out(project: ProjectConfig) -> ProjectConfigOut:
    """Convert a ProjectConfig model to its output schema, computing derived fields."""
    out = ProjectConfigOut.model_validate(project)
    out.has_git_provider_token = bool(project.git_provider_token_enc)
    return out


def _get_repo(db: AsyncSession = Depends(get_db)) -> ProjectConfigRepository:
    return ProjectConfigRepository(db)


@router.get("/projects", response_model=list[ProjectConfigOut])
async def list_projects(repo: ProjectConfigRepository = Depends(_get_repo)):
    projects = await repo.list_all()
    return [_project_out(p) for p in projects]


@router.post("/projects/parse-git-url", response_model=GitUrlParseResponse)
async def parse_git_url_endpoint(
    body: GitUrlParseRequest,
    db: AsyncSession = Depends(get_db),
):
    """Parse a git URL and detect the default branch.

    When ``workspace_server_id`` is provided, uses ``git ls-remote`` on the
    workspace server via SSH — the server may have access to repos that the
    backend cannot reach directly.  Falls back to provider HTTP API otherwise.
    """
    try:
        parsed = parse_git_url(body.git_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    default_branch: str | None = None

    # Try SSH-based detection through the workspace server first
    if body.workspace_server_id:
        server_repo = WorkspaceServerRepository(db)
        server = await server_repo.get_by_id(body.workspace_server_id)
        if server:
            ssh = SSHService.for_server(server)
            with contextlib.suppress(Exception):
                default_branch = await get_default_branch_via_ssh(ssh, body.git_url)

    # Fallback: direct provider HTTP API
    if default_branch is None:
        try:
            client = get_http_client()
            default_branch = await get_default_branch(
                parsed.provider, parsed.owner, parsed.repo, client
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Provider API error {exc.response.status_code}: {exc.response.text[:200]}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to reach provider API: {exc}",
            ) from exc

    slug = f"{parsed.owner}-{parsed.repo}".lower().replace("_", "-")
    return GitUrlParseResponse(
        provider=parsed.provider,
        owner=parsed.owner,
        repo=parsed.repo,
        host=parsed.host,
        default_branch=default_branch,
        suggested_slug=slug,
        suggested_id=slug,
        provider_confirmed=parsed.provider != "unknown",
    )


@router.post("/projects/test-connection", response_model=TestConnectionResponse)
async def test_connection_endpoint(
    body: TestConnectionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Test SSH connectivity from a workspace server to the git repo."""
    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(body.workspace_server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Workspace server not found")

    ssh = SSHService.for_server(server)
    try:
        stdout, stderr, exit_code = await ssh.run_command(
            f"git ls-remote {body.git_url} HEAD",
            timeout=10,
        )
        if exit_code == 0:
            return TestConnectionResponse(success=True)
        error_detail = stderr.strip() or stdout.strip() or f"exit code {exit_code}"
        return TestConnectionResponse(success=False, error=error_detail)
    except Exception as exc:
        return TestConnectionResponse(success=False, error=str(exc))


@router.get("/projects/{project_id:path}", response_model=ProjectConfigOut)
async def get_project(
    project_id: str,
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return _project_out(project)


@router.post("/projects", response_model=ProjectConfigOut, status_code=201)
async def create_project(
    body: ProjectConfigCreate,
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    existing = await repo.get_by_id(body.project_id)
    if existing:
        raise HTTPException(409, "Project already exists")

    detected_branch: str | None = None

    # Step 1: If workspace server is provided, verify repo via SSH first
    if body.workspace_server_id:
        server_repo = WorkspaceServerRepository(repo._session)
        server = await server_repo.get_by_id(body.workspace_server_id)
        if not server:
            raise HTTPException(422, f"Workspace server {body.workspace_server_id} not found")

        git_url = f"git@{_provider_host(body.git_provider)}:{body.repo_owner}/{body.repo_name}.git"
        ssh = SSHService.for_server(server)
        try:
            detected_branch = await get_default_branch_via_ssh(ssh, git_url)
        except Exception as exc:
            raise HTTPException(422, f"SSH repo verification failed: {exc}") from exc

    # Step 2: Fallback to direct provider HTTP API if no SSH or no server
    if detected_branch is None:
        client = get_http_client()
        try:
            detected_branch = await get_default_branch(
                body.git_provider, body.repo_owner, body.repo_name, client
            )
        except ValueError as exc:
            raise HTTPException(422, f"Cannot verify repo: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                detail = (
                    f"Authentication failed for {body.git_provider} — check token configuration"
                )
            elif status == 404:
                detail = f"Repository {body.repo_owner}/{body.repo_name} not found on {body.git_provider}"
            else:
                detail = f"Repo verification failed ({status})"
            raise HTTPException(422, detail) from exc
        except httpx.RequestError as exc:
            raise HTTPException(422, f"Cannot reach {body.git_provider} API: {exc}") from exc

    # Step 3: Save project
    data = body.model_dump()
    data["default_branch"] = detected_branch
    # Encrypt git_provider_token if provided
    raw_token = data.pop("git_provider_token", None)
    if raw_token:
        data["git_provider_token_enc"] = encrypt_value(raw_token)
    project = ProjectConfig(**data)
    created = await repo.create(project)
    return _project_out(created)


@router.put("/projects/{project_id:path}", response_model=ProjectConfigOut)
async def update_project(
    project_id: str,
    body: ProjectConfigUpdate,
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    data = body.model_dump(exclude_unset=True)
    # Encrypt git_provider_token if provided
    raw_token = data.pop("git_provider_token", None)
    if raw_token is not None:
        data["git_provider_token_enc"] = encrypt_value(raw_token) if raw_token else None
    updated = await repo.update(project, data)
    return _project_out(updated)


@router.delete("/projects/{project_id:path}", status_code=204)
async def delete_project(
    project_id: str,
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    await repo.delete(project)
