# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Endpoint for fetching issues from a project's git provider."""

import contextlib
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas.projects import GitIssueOut
from backend.services.encryption import decrypt_value
from backend.services.git.protocol import get_git_provider
from backend.services.http_client import get_http_client
from backend.services.workspace.ssh_service import SSHService

from .projects import _get_repo

logger = logging.getLogger("autodev.project_issues")
router = APIRouter(tags=["projects"])


def _build_api_url(provider: str, repo_path: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """Build API URL, headers, and query params for issue listing."""
    if provider == "github":
        return (
            f"{settings.github_api_url}/repos/{repo_path}/issues",
            {"Authorization": f"token {settings.github_token}"} if settings.github_token else {},
            {"state": "open", "per_page": "30"},
        )
    if provider == "gitlab":
        import urllib.parse

        encoded = urllib.parse.quote(repo_path, safe="")
        return (
            f"{settings.gitlab_api_url}/api/v4/projects/{encoded}/issues",
            {"PRIVATE-TOKEN": settings.gitlab_token} if settings.gitlab_token else {},
            {"state": "opened", "per_page": "30"},
        )
    if provider == "bitbucket":
        return (
            f"{settings.bitbucket_base_url}/2.0/repositories/{repo_path}/issues",
            {},
            {"state": "open", "pagelen": "30"},
        )
    # Default: gitea
    return (
        f"{settings.gitea_url}/api/v1/repos/{repo_path}/issues",
        {"Authorization": f"token {settings.gitea_token}"} if settings.gitea_token else {},
        {"state": "open", "limit": "30", "type": "issues"},
    )


def _parse_issues(provider: str, raw: list[dict]) -> list[dict]:
    """Normalize raw API response to GitIssueOut shape."""
    issues = []
    for item in raw:
        if provider == "github" and item.get("pull_request"):
            continue
        issues.append(
            {
                "number": item["number"],
                "title": item.get("title", ""),
                "body": item.get("body", "") or "",
                "labels": [
                    la.get("name", "") if isinstance(la, dict) else str(la)
                    for la in item.get("labels", [])
                ],
                "url": item.get("html_url", item.get("web_url", "")),
                "state": item.get("state", "open"),
            }
        )
    return issues


async def _fetch_issues_via_ssh(ssh: SSHService, provider: str, repo_path: str) -> list[dict]:
    """Fetch issues by running curl on the workspace server."""
    url, headers, params = _build_api_url(provider, repo_path)

    # Build curl command
    query = "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}?{query}" if query else url

    header_args = " ".join(f'-H "{k}: {v}"' for k, v in headers.items())
    cmd = f"curl -sf {header_args} '{full_url}'"

    stdout, stderr, rc = await ssh.run_command(cmd, timeout=30)
    if rc != 0:
        raise RuntimeError(f"curl failed (rc={rc}): {stderr.strip()}")

    raw = json.loads(stdout)
    if not isinstance(raw, list):
        raw = raw.get("values", raw.get("issues", []))
    return _parse_issues(provider, raw)


@router.get("/projects/{project_id:path}/issues", response_model=list[GitIssueOut])
async def list_project_issues(
    project_id: str,
    repo: ProjectConfigRepository = Depends(_get_repo),
    db: AsyncSession = Depends(get_db),
):
    """Fetch open issues from the project's git provider."""
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if project.task_source == "plain":
        return []

    repo_path = f"{project.repo_owner}/{project.repo_name}"

    # If project is linked to a workspace server, fetch through SSH
    if project.workspace_server_id:
        server_repo = WorkspaceServerRepository(db)
        server = await server_repo.get_by_id(project.workspace_server_id)
        if server:
            try:
                ssh = SSHService.for_server(server)
                return await _fetch_issues_via_ssh(ssh, project.git_provider, repo_path)
            except Exception as exc:
                logger.warning(
                    "SSH issue fetch failed for %s (server %d), falling back to direct: %s",
                    project_id,
                    server.id,
                    exc,
                )

    # Fallback: direct HTTP from backend
    project_token = None
    if project.git_provider_token_enc:
        with contextlib.suppress(Exception):
            project_token = decrypt_value(project.git_provider_token_enc)
    client = get_http_client()
    provider = get_git_provider(project.git_provider, client, access_token=project_token)

    try:
        return await provider.list_issues(repo_path)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise HTTPException(
                502, f"Auth failed for {project.git_provider}: check token config"
            ) from exc
        raise HTTPException(502, f"Provider API error: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Cannot reach {project.git_provider} API: {exc}") from exc