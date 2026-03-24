# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""MCP tools — Tier 1: Project and task run management."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import Context

_BASE_URL = os.environ.get("AGENTICKODE_URL", "http://localhost:8000")


async def _api(ctx: Context, method: str, path: str, **kwargs) -> Any:
    """Call the platform REST API."""
    url = f"{_BASE_URL}/api{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await getattr(client, method)(url, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204:
            return {"status": "ok"}
        return resp.json()


async def list_projects(ctx: Context, status: str | None = None) -> list:
    """List all projects. Optionally filter by status (active/archived)."""
    params = {}
    if status:
        params["status"] = status
    return await _api(ctx, "get", "/projects", params=params)


async def get_project(ctx: Context, project_id: str) -> dict:
    """Get detailed information about a project including config and recent runs."""
    return await _api(ctx, "get", f"/projects/{project_id}")


async def create_project(
    ctx: Context,
    repo_url: str,
    git_provider: str,
    name: str | None = None,
    execution_mode: str | None = None,
) -> dict:
    """Create a new project from a git repository URL.

    Args:
        repo_url: Full git repository URL (e.g. https://github.com/org/repo)
        git_provider: One of: github, gitlab, gitea, bitbucket
        name: Project name (auto-detected from URL if omitted)
        execution_mode: One of: structured, autonomous, hybrid
    """
    body: dict = {"repo_url": repo_url, "git_provider": git_provider}
    if name:
        body["project_id"] = name
    if execution_mode:
        body["autonomy_config"] = {"execution_mode": execution_mode}
    return await _api(ctx, "post", "/projects", json=body)


async def update_project(
    ctx: Context,
    project_id: str,
    execution_mode: str | None = None,
    episode_config: str | None = None,
) -> dict:
    """Update project settings.

    Args:
        project_id: The project to update
        execution_mode: Set mode (structured/autonomous/hybrid)
        episode_config: JSON string of episode settings, e.g. '{"max_episodes":5}'
    """
    import json

    body: dict = {}
    ac: dict = {}
    if execution_mode:
        ac["execution_mode"] = execution_mode
    if episode_config:
        ac["episode_config"] = json.loads(episode_config)
    if ac:
        body["autonomy_config"] = ac
    return await _api(ctx, "put", f"/projects/{project_id}", json=body)


async def create_run(
    ctx: Context,
    project_id: str,
    title: str,
    description: str = "",
    execution_mode: str | None = None,
) -> dict:
    """Create and queue a new task run for a project.

    Args:
        project_id: The project to run the task on
        title: Short task title
        description: Detailed task description
        execution_mode: Override mode (structured/autonomous/hybrid)
    """
    body: dict = {
        "project_id": project_id,
        "title": title,
        "description": description,
    }
    if execution_mode:
        body["execution_mode"] = execution_mode
    return await _api(ctx, "post", "/runs", json=body)


async def list_runs(
    ctx: Context,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict:
    """List task runs with optional filters.

    Args:
        project_id: Filter by project
        status: Filter by status (pending/running/completed/failed)
        limit: Maximum results (default 20)
    """
    params: dict = {"limit": limit}
    if project_id:
        params["project_id"] = project_id
    if status:
        params["status"] = status
    return await _api(ctx, "get", "/runs", params=params)


async def get_run(ctx: Context, run_id: int) -> dict:
    """Get full details of a task run including phases, episodes, and results."""
    return await _api(ctx, "get", f"/runs/{run_id}")


async def get_run_logs(ctx: Context, run_id: int, tail: int = 50) -> dict:
    """Get recent log entries for a task run."""
    return await _api(ctx, "get", f"/runs/{run_id}", params={"limit": tail})


async def cancel_run(ctx: Context, run_id: int) -> dict:
    """Cancel a running or pending task run."""
    return await _api(ctx, "post", f"/runs/{run_id}/cancel")
