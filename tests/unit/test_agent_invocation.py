# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for AgentInvocation model and API endpoints."""

from datetime import UTC, datetime

import pytest

from backend.models import AgentInvocation, ProjectConfig


class TestAgentInvocationModel:
    async def test_create_invocation(self, db_session, make_task_run):
        """AgentInvocation can be created and persisted."""
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        inv = AgentInvocation(
            run_id=run.id,
            agent_name="claude",
            phase_name="coding",
            subtask_index=0,
            subtask_title="Implement feature",
            prompt_text="Write some code",
            system_prompt_text="You are a developer",
            prompt_chars=14,
            response_chars=0,
            status="running",
            started_at=datetime.now(UTC),
        )
        db_session.add(inv)
        await db_session.commit()

        assert inv.id is not None
        assert inv.run_id == run.id
        assert inv.agent_name == "claude"
        assert inv.phase_name == "coding"
        assert inv.status == "running"

    async def test_invocation_cascade_delete(self, db_session, make_task_run):
        """AgentInvocation is deleted when the TaskRun is deleted."""
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        inv = AgentInvocation(
            run_id=run.id,
            agent_name="ollama/qwen2.5",
            phase_name="planning",
            prompt_chars=100,
            response_chars=200,
            status="success",
            started_at=datetime.now(UTC),
        )
        db_session.add(inv)
        await db_session.commit()
        inv_id = inv.id

        await db_session.delete(run)
        await db_session.commit()

        from sqlalchemy import select

        result = await db_session.execute(
            select(AgentInvocation).where(AgentInvocation.id == inv_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_invocation_complete_fields(self, db_session, make_task_run):
        """AgentInvocation stores all fields correctly."""
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        now = datetime.now(UTC)
        inv = AgentInvocation(
            run_id=run.id,
            agent_name="claude",
            phase_name="coding",
            subtask_index=2,
            subtask_title="Write tests",
            prompt_text="Write unit tests",
            response_text="Here are the tests",
            system_prompt_text="You are a tester",
            prompt_chars=16,
            response_chars=18,
            exit_code=0,
            files_changed=["tests/test_foo.py"],
            duration_seconds=42.5,
            status="success",
            error_message=None,
            started_at=now,
            completed_at=now,
            metadata_={"command": "claude --no-stream"},
        )
        db_session.add(inv)
        await db_session.commit()

        assert inv.exit_code == 0
        assert inv.files_changed == ["tests/test_foo.py"]
        assert inv.duration_seconds == 42.5
        assert inv.metadata_ == {"command": "claude --no-stream"}


class TestRunInvocationsAPI:
    async def test_list_invocations_empty(self, client, db_session, make_task_run):
        """GET /runs/{id}/invocations returns empty list when no invocations exist."""
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        resp = await client.get(f"/api/runs/{run.id}/invocations")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_invocations_returns_records(self, client, db_session, make_task_run):
        """GET /runs/{id}/invocations returns invocations ordered by started_at."""
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        for i in range(3):
            inv = AgentInvocation(
                run_id=run.id,
                agent_name="claude",
                phase_name="coding",
                subtask_index=i,
                subtask_title=f"Subtask {i}",
                prompt_chars=100 + i,
                response_chars=200 + i,
                status="success",
                started_at=datetime.now(UTC),
            )
            db_session.add(inv)
        await db_session.commit()

        resp = await client.get(f"/api/runs/{run.id}/invocations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        # Verify list view does NOT include full prompt/response text
        for item in data:
            assert "prompt_text" not in item
            assert "response_text" not in item
            assert "system_prompt_text" not in item

    async def test_list_invocations_has_correct_columns(self, client, db_session, make_task_run):
        """GET /runs/{id}/invocations returns all expected fields."""
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        inv = AgentInvocation(
            run_id=run.id,
            agent_name="ollama/qwen2.5",
            phase_name="reviewing",
            subtask_index=0,
            subtask_title="Review attempt 1",
            prompt_chars=500,
            response_chars=300,
            exit_code=None,
            files_changed=None,
            duration_seconds=15.3,
            status="success",
            started_at=datetime.now(UTC),
        )
        db_session.add(inv)
        await db_session.commit()

        resp = await client.get(f"/api/runs/{run.id}/invocations")
        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["agent_name"] == "ollama/qwen2.5"
        assert item["phase_name"] == "reviewing"
        assert item["prompt_chars"] == 500
        assert item["response_chars"] == 300
        assert item["duration_seconds"] == pytest.approx(15.3)
        assert item["status"] == "success"

    async def test_get_invocation_detail_includes_text(self, client, db_session, make_task_run):
        """GET /runs/{id}/invocations/{inv_id} returns full prompt/response text."""
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        inv = AgentInvocation(
            run_id=run.id,
            agent_name="claude",
            phase_name="planning",
            prompt_text="Plan the task",
            response_text="Here is the plan",
            system_prompt_text="You are a planner",
            prompt_chars=13,
            response_chars=17,
            status="success",
            started_at=datetime.now(UTC),
        )
        db_session.add(inv)
        await db_session.commit()

        resp = await client.get(f"/api/runs/{run.id}/invocations/{inv.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prompt_text"] == "Plan the task"
        assert data["response_text"] == "Here is the plan"
        assert data["system_prompt_text"] == "You are a planner"

    async def test_get_invocation_detail_not_found(self, client, db_session, make_task_run):
        """GET /runs/{id}/invocations/{inv_id} returns 404 when not found."""
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        resp = await client.get(f"/api/runs/{run.id}/invocations/9999")
        assert resp.status_code == 404

    async def test_get_invocation_detail_wrong_run(self, client, db_session, make_task_run):
        """GET /runs/{id}/invocations/{inv_id} returns 404 if invocation belongs to another run."""
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run1 = make_task_run(task_id="TASK-1")
        run2 = make_task_run(task_id="TASK-2")
        db_session.add(run1)
        db_session.add(run2)
        await db_session.commit()

        inv = AgentInvocation(
            run_id=run1.id,
            agent_name="claude",
            phase_name="coding",
            prompt_chars=10,
            response_chars=20,
            status="success",
            started_at=datetime.now(UTC),
        )
        db_session.add(inv)
        await db_session.commit()

        # Access via wrong run_id
        resp = await client.get(f"/api/runs/{run2.id}/invocations/{inv.id}")
        assert resp.status_code == 404


class TestWorkspaceServerInvocationsAPI:
    async def test_list_server_invocations_empty(self, client, db_session, make_task_run):
        """GET /workspace-servers/{id}/invocations returns empty list."""
        from backend.models import WorkspaceServer

        server = WorkspaceServer(
            name="ws-01",
            hostname="192.168.1.1",
            port=22,
            username="root",
        )
        db_session.add(server)
        await db_session.commit()

        resp = await client.get(f"/api/workspace-servers/{server.id}/invocations")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_server_invocations_filtered_by_agent(
        self, client, db_session, make_task_run
    ):
        """GET /workspace-servers/{id}/invocations?agent_name filters correctly."""
        from backend.models import WorkspaceServer

        server = WorkspaceServer(
            name="ws-01",
            hostname="192.168.1.1",
            port=22,
            username="root",
        )
        db_session.add(server)
        await db_session.commit()

        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        for agent_name in ["claude", "ollama/qwen2.5", "claude"]:
            inv = AgentInvocation(
                run_id=run.id,
                workspace_server_id=server.id,
                agent_name=agent_name,
                phase_name="coding",
                prompt_chars=100,
                response_chars=200,
                status="success",
                started_at=datetime.now(UTC),
            )
            db_session.add(inv)
        await db_session.commit()

        resp = await client.get(f"/api/workspace-servers/{server.id}/invocations?agent_name=claude")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(item["agent_name"] == "claude" for item in data)