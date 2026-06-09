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
    WorkspaceReadinessItem,
    WorkspaceReadinessResponse,
)
from backend.services.encryption import encrypt_value
from backend.services.git.repo_info import get_default_branch, get_default_branch_via_ssh
from backend.services.git.url_parser import parse_git_url
from backend.services.http_client import get_http_client
from backend.services.workspace.command_executor import executor_for_server

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


_INTEGRATION_SECRET_KEYS = ("notion_api_key", "plane_api_key")


def _encrypt_integration_secrets(integration_config: dict | None) -> dict | None:
    """Encrypt plaintext secret fields inside integration_config in place.

    Plaintext keys like ``notion_api_key`` are encrypted and re-stored as
    ``notion_api_key_enc`` so we never persist secrets in the clear.
    """
    if not integration_config:
        return integration_config
    cfg = dict(integration_config)
    for key in _INTEGRATION_SECRET_KEYS:
        raw = cfg.pop(key, None)
        if raw:
            cfg[f"{key}_enc"] = encrypt_value(str(raw))
    return cfg


def _project_out(project: ProjectConfig) -> ProjectConfigOut:
    """Convert a ProjectConfig model to its output schema, computing derived fields."""
    out = ProjectConfigOut.model_validate(project)
    out.has_git_provider_token = bool(project.git_provider_token_enc)
    out.workspace_server_ids = [ws.workspace_server_id for ws in project.workspace_servers]
    # Redact secrets when echoing integration_config back to clients.
    stored: dict = project.integration_config or {}  # type: ignore[assignment]
    cfg: dict = {k: v for k, v in stored.items() if k not in _INTEGRATION_SECRET_KEYS}
    for key in _INTEGRATION_SECRET_KEYS:
        cfg.pop(f"{key}_enc", None)
        cfg[f"has_{key}"] = bool(stored.get(f"{key}_enc"))
    out.integration_config = cfg
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
            ssh = executor_for_server(server)
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

    ssh = executor_for_server(server)
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


@router.get(
    "/projects/{project_id:path}/workspace-readiness",
    response_model=WorkspaceReadinessResponse,
)
async def check_workspace_readiness(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Check if a project is cloned and ready on each assigned workspace."""
    repo = ProjectConfigRepository(db)
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    server_repo = WorkspaceServerRepository(db)
    items: list[WorkspaceReadinessItem] = []

    for pws in project.workspace_servers:
        server = await server_repo.get_by_id(pws.workspace_server_id)
        if not server:
            continue

        # Resolve expected project path on workspace
        raw_path = project.workspace_path or project.repo_name
        if raw_path.startswith("/"):
            expected_path = raw_path
        else:
            root = server.workspace_root or "/home/workspace"
            expected_path = f"{root}/{raw_path}".rstrip("/")

        ssh = executor_for_server(server)
        try:
            stdout, _stderr, rc = await ssh.run_command(
                f"test -d {expected_path}/.git && echo 'exists' || echo 'missing'",
                timeout=10,
            )
            if "exists" in stdout:
                items.append(
                    WorkspaceReadinessItem(
                        server_id=server.id,
                        server_name=server.name,
                        status="ready",
                        path=expected_path,
                        worker_user=server.worker_user,
                    )
                )
            else:
                items.append(
                    WorkspaceReadinessItem(
                        server_id=server.id,
                        server_name=server.name,
                        status="not_cloned",
                        path=expected_path,
                        worker_user=server.worker_user,
                    )
                )
        except Exception as exc:
            items.append(
                WorkspaceReadinessItem(
                    server_id=server.id,
                    server_name=server.name,
                    status="unreachable",
                    error=str(exc)[:200],
                    worker_user=server.worker_user,
                )
            )

    return WorkspaceReadinessResponse(project_id=project_id, workspaces=items)


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

    # Step 1: If workspace servers are provided, verify repo via SSH using the first one
    first_server_id = body.workspace_server_ids[0] if body.workspace_server_ids else None
    if first_server_id:
        server_repo = WorkspaceServerRepository(repo._session)
        server = await server_repo.get_by_id(first_server_id)
        if not server:
            raise HTTPException(422, f"Workspace server {first_server_id} not found")

        git_url = f"git@{_provider_host(body.git_provider)}:{body.repo_owner}/{body.repo_name}.git"
        ssh = executor_for_server(server)
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
    if "integration_config" in data:
        data["integration_config"] = _encrypt_integration_secrets(data["integration_config"]) or {}
    # workspace_server_ids stored via join table, not as a model column
    workspace_server_ids = data.pop("workspace_server_ids", [])
    project = ProjectConfig(**data)
    created = await repo.create(project, workspace_server_ids=workspace_server_ids)
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
    if "integration_config" in data:
        # Merge with existing so partial updates don't wipe the stored secret.
        merged = {**(project.integration_config or {}), **(data["integration_config"] or {})}
        data["integration_config"] = _encrypt_integration_secrets(merged) or {}
    # workspace_server_ids is handled by the repository via the join table
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
