# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for GET /workspace-servers/{server_id}/invocations with filters + pagination."""

from datetime import UTC, datetime

from backend.models import AgentInvocation, TaskRun, WorkspaceServer


async def _seed(db_session, server_id: int, run_id: int, count: int = 5):
    """Create a workspace server, task run, and N invocations."""
    ws = WorkspaceServer(
        id=server_id,
        name="ws-1",
        hostname="10.0.0.1",
        port=22,
        username="root",
        workspace_root="/workspaces",
        status="online",
    )
    db_session.add(ws)
    tr = TaskRun(
        id=run_id,
        task_id="TASK-1",
        project_id="proj-1",
        title="Test",
        description="desc",
        branch_name="feature/test",
        workspace_path="/workspaces/proj",
        repo_owner="org",
        repo_name="repo",
        default_branch="main",
        task_source="test",
        git_provider="gitea",
        task_source_meta={},
        status="running",
        max_retries=3,
    )
    db_session.add(tr)
    await db_session.flush()

    for i in range(count):
        inv = AgentInvocation(
            run_id=run_id,
            workspace_server_id=server_id,
            agent_name="agent/claude" if i % 2 == 0 else "ollama/qwen",
            phase_name="coding" if i < 3 else "reviewing",
            status="success" if i != 2 else "failed",
            prompt_chars=100,
            response_chars=200,
            started_at=datetime(2026, 1, 1, 12, i, 0, tzinfo=UTC),
        )
        db_session.add(inv)
    await db_session.commit()


class TestListServerInvocations:
    async def test_basic(self, client, db_session):
        await _seed(db_session, server_id=1, run_id=1, count=3)
        resp = await client.get("/api/workspace-servers/1/invocations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    async def test_agent_filter(self, client, db_session):
        await _seed(db_session, server_id=1, run_id=1, count=5)
        resp = await client.get("/api/workspace-servers/1/invocations?agent_name=agent/claude")
        assert resp.status_code == 200
        data = resp.json()
        assert all(d["agent_name"] == "agent/claude" for d in data)
        assert len(data) == 3  # indices 0, 2, 4

    async def test_phase_filter(self, client, db_session):
        await _seed(db_session, server_id=1, run_id=1, count=5)
        resp = await client.get("/api/workspace-servers/1/invocations?phase_name=reviewing")
        assert resp.status_code == 200
        data = resp.json()
        assert all(d["phase_name"] == "reviewing" for d in data)
        assert len(data) == 2  # indices 3, 4

    async def test_status_filter(self, client, db_session):
        await _seed(db_session, server_id=1, run_id=1, count=5)
        resp = await client.get("/api/workspace-servers/1/invocations?status=failed")
        assert resp.status_code == 200
        data = resp.json()
        assert all(d["status"] == "failed" for d in data)
        assert len(data) == 1  # index 2

    async def test_offset_pagination(self, client, db_session):
        await _seed(db_session, server_id=1, run_id=1, count=5)
        resp1 = await client.get("/api/workspace-servers/1/invocations?limit=2&offset=0")
        assert resp1.status_code == 200
        page1 = resp1.json()
        assert len(page1) == 2

        resp2 = await client.get("/api/workspace-servers/1/invocations?limit=2&offset=2")
        assert resp2.status_code == 200
        page2 = resp2.json()
        assert len(page2) == 2

        resp3 = await client.get("/api/workspace-servers/1/invocations?limit=2&offset=4")
        assert resp3.status_code == 200
        page3 = resp3.json()
        assert len(page3) == 1

        # No overlap between pages
        all_ids = [i["id"] for i in page1 + page2 + page3]
        assert len(all_ids) == len(set(all_ids))

    async def test_empty_server(self, client, db_session):
        """Server with no invocations returns empty list."""
        ws = WorkspaceServer(
            id=99,
            name="ws-empty",
            hostname="10.0.0.99",
            port=22,
            username="root",
            workspace_root="/workspaces",
            status="online",
        )
        db_session.add(ws)
        await db_session.commit()

        resp = await client.get("/api/workspace-servers/99/invocations")
        assert resp.status_code == 200
        assert resp.json() == []