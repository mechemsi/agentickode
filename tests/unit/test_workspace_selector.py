# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for workspace selector service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ProjectConfig, ProjectWorkspaceServer, TaskRun, WorkspaceServer
from backend.services.workspace.workspace_selector import select_workspace_for_run

# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

_ws_counter = 0
_proj_counter = 0


@pytest.fixture()
def make_workspace_server(db_session: AsyncSession):
    """Factory: create and persist a WorkspaceServer, returning the instance."""
    counter = {"n": 0}

    async def _factory(**overrides):
        counter["n"] += 1
        n = counter["n"]
        defaults = {
            "name": f"ws-{n}",
            "hostname": f"host-{n}",
            "port": 22,
            "username": "root",
            "workspace_root": "/workspaces",
            "status": "ready",
        }
        defaults.update(overrides)
        ws = WorkspaceServer(**defaults)
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)
        return ws

    return _factory


@pytest.fixture()
def make_project_config(db_session: AsyncSession):
    """Factory: create and persist a ProjectConfig, optionally linking workspace servers."""
    counter = {"n": 0}

    async def _factory(workspace_server_ids: list[int] | None = None, **overrides):
        counter["n"] += 1
        n = counter["n"]
        defaults = {
            "project_id": f"proj-{n}",
            "project_slug": f"project-{n}",
            "repo_owner": "org",
            "repo_name": f"repo-{n}",
            "default_branch": "main",
            "task_source": "plane",
            "git_provider": "gitea",
        }
        defaults.update(overrides)
        project = ProjectConfig(**defaults)
        db_session.add(project)
        await db_session.flush()  # get project_id into DB before FK inserts

        for priority, ws_id in enumerate(workspace_server_ids or []):
            pws = ProjectWorkspaceServer(
                project_id=project.project_id,
                workspace_server_id=ws_id,
                priority=priority,
            )
            db_session.add(pws)

        await db_session.commit()
        await db_session.refresh(project)
        return project

    return _factory


@pytest.fixture()
def make_persisted_task_run(db_session: AsyncSession):
    """Factory: create and persist a TaskRun."""
    counter = {"n": 0}

    async def _factory(**overrides):
        counter["n"] += 1
        n = counter["n"]
        defaults = {
            "task_id": f"TASK-{n}",
            "title": f"Task {n}",
            "description": "Test",
            "branch_name": f"feature/ai-TASK-{n}",
            "workspace_path": "/workspaces/proj",
            "repo_owner": "org",
            "repo_name": "repo",
            "default_branch": "main",
            "task_source": "plane",
            "git_provider": "gitea",
            "task_source_meta": {},
            "status": "pending",
            "max_retries": 3,
        }
        defaults.update(overrides)
        run = TaskRun(**defaults)
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)
        return run

    return _factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_none_when_no_servers_assigned(
    db_session: AsyncSession,
    make_project_config,
):
    project = await make_project_config()
    result = await select_workspace_for_run(project.project_id, db_session)
    assert result is None


@pytest.mark.asyncio
async def test_returns_only_server_when_one_assigned(
    db_session: AsyncSession,
    make_project_config,
    make_workspace_server,
):
    ws = await make_workspace_server()
    project = await make_project_config(workspace_server_ids=[ws.id])
    result = await select_workspace_for_run(project.project_id, db_session)
    assert result == ws.id


@pytest.mark.asyncio
async def test_selects_least_loaded_server(
    db_session: AsyncSession,
    make_project_config,
    make_workspace_server,
    make_persisted_task_run,
):
    ws1 = await make_workspace_server()
    ws2 = await make_workspace_server()
    project = await make_project_config(workspace_server_ids=[ws1.id, ws2.id])
    # ws1 has 2 active runs, ws2 has 0
    await make_persisted_task_run(
        project_id=project.project_id, workspace_server_id=ws1.id, status="running"
    )
    await make_persisted_task_run(
        project_id=project.project_id, workspace_server_id=ws1.id, status="pending"
    )
    result = await select_workspace_for_run(project.project_id, db_session)
    assert result == ws2.id


@pytest.mark.asyncio
async def test_respects_priority_when_equal_load(
    db_session: AsyncSession,
    make_project_config,
    make_workspace_server,
):
    ws1 = await make_workspace_server()
    ws2 = await make_workspace_server()
    # ws1 has priority 1, ws2 has priority 0 (lower number = higher priority)
    project = await make_project_config(workspace_server_ids=[ws1.id, ws2.id])
    # Update priorities: ws1 -> 1, ws2 -> 0
    pws1 = await db_session.get(ProjectWorkspaceServer, (project.project_id, ws1.id))
    pws2 = await db_session.get(ProjectWorkspaceServer, (project.project_id, ws2.id))
    pws1.priority = 1
    pws2.priority = 0
    await db_session.commit()
    result = await select_workspace_for_run(project.project_id, db_session)
    assert result == ws2.id


@pytest.mark.asyncio
async def test_excludes_specified_servers(
    db_session: AsyncSession,
    make_project_config,
    make_workspace_server,
):
    ws1 = await make_workspace_server()
    ws2 = await make_workspace_server()
    project = await make_project_config(workspace_server_ids=[ws1.id, ws2.id])
    result = await select_workspace_for_run(
        project.project_id, db_session, exclude_server_ids=[ws1.id]
    )
    assert result == ws2.id


@pytest.mark.asyncio
async def test_ignores_completed_runs_in_load_count(
    db_session: AsyncSession,
    make_project_config,
    make_workspace_server,
    make_persisted_task_run,
):
    ws1 = await make_workspace_server()
    ws2 = await make_workspace_server()
    project = await make_project_config(workspace_server_ids=[ws1.id, ws2.id])
    # ws2 has completed/failed runs (should not count toward load)
    await make_persisted_task_run(
        project_id=project.project_id, workspace_server_id=ws2.id, status="completed"
    )
    await make_persisted_task_run(
        project_id=project.project_id, workspace_server_id=ws2.id, status="failed"
    )
    # ws1 has 1 active run
    await make_persisted_task_run(
        project_id=project.project_id, workspace_server_id=ws1.id, status="running"
    )
    result = await select_workspace_for_run(project.project_id, db_session)
    assert result == ws2.id
