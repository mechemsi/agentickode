# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.worker.steps.agent_step.run_agent_step."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models import PhaseExecution, ProjectConfig
from backend.worker.steps.agent_step import run_agent_step


def _make_resolved(adapter, role="coder"):
    """Mimics the ResolvedRole shape returned by RoleResolver.resolve."""
    resolved = MagicMock()
    resolved.adapter = adapter
    resolved.role_config = None
    resolved.agent_settings = None
    resolved.tried = []
    resolved.is_fallback = False
    return resolved


class TestAgentStep:
    async def test_generate_mode_default(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-as1", project_slug="as1", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-as1")
        db_session.add(run)
        await db_session.commit()

        adapter = MagicMock()
        adapter.provider_name = "agent/claude"
        adapter.generate = AsyncMock(return_value="The answer is 42")
        mock_services.role_resolver.resolve = AsyncMock(return_value=_make_resolved(adapter))

        phase_config = {
            "phase_name": "ask",
            "kind": "agent",
            "params": {"prompt": "What is the answer?"},
        }
        result = await run_agent_step(run, db_session, mock_services, phase_config)

        assert result["provider"] == "agent/claude"
        assert result["mode"] == "generate"
        assert result["response"] == "The answer is 42"
        assert result["prompt"] == "What is the answer?"
        adapter.generate.assert_awaited_once()

    async def test_task_mode_calls_run_task(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-as2", project_slug="as2", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-as2", workspace_path="/workspaces/proj-as2")
        db_session.add(run)
        await db_session.commit()

        adapter = MagicMock()
        adapter.provider_name = "agent/codex"
        adapter.run_task = AsyncMock(
            return_value={"exit_code": 0, "files_changed": ["a.py"], "session_id": "sess-1"}
        )
        mock_services.role_resolver.resolve = AsyncMock(return_value=_make_resolved(adapter))

        phase_config = {
            "phase_name": "implement",
            "kind": "agent",
            "params": {"prompt": "fix the thing", "mode": "task"},
        }
        result = await run_agent_step(run, db_session, mock_services, phase_config)

        assert result["mode"] == "task"
        assert result["response"]["exit_code"] == 0
        assert result["response"]["files_changed"] == ["a.py"]
        assert result["session_id"] == "sess-1"
        adapter.run_task.assert_awaited_once()
        # First positional arg is workspace
        assert adapter.run_task.call_args[0][0] == "/workspaces/proj-as2"

    async def test_prompt_template_substitution(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-as3", project_slug="as3", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-as3", title="Add login")
        db_session.add(run)
        await db_session.commit()

        adapter = MagicMock()
        adapter.provider_name = "agent/claude"
        adapter.generate = AsyncMock(return_value="ok")
        mock_services.role_resolver.resolve = AsyncMock(return_value=_make_resolved(adapter))

        phase_config = {
            "phase_name": "ask",
            "kind": "agent",
            "params": {"prompt": "Help with: {{run.title}}"},
        }
        result = await run_agent_step(run, db_session, mock_services, phase_config)

        assert result["prompt"] == "Help with: Add login"
        # First positional arg to generate is the rendered prompt
        assert adapter.generate.call_args[0][0] == "Help with: Add login"

    async def test_step_output_substitution(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-as4", project_slug="as4", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-as4")
        db_session.add(run)
        await db_session.commit()
        prior = PhaseExecution(
            run_id=run.id,
            phase_name="scan",
            order_index=0,
            status="completed",
            result={"vuln_count": 3},
        )
        db_session.add(prior)
        await db_session.commit()

        adapter = MagicMock()
        adapter.provider_name = "agent/claude"
        adapter.generate = AsyncMock(return_value="ok")
        mock_services.role_resolver.resolve = AsyncMock(return_value=_make_resolved(adapter))

        phase_config = {
            "phase_name": "fix",
            "kind": "agent",
            "params": {"prompt": "Fix {{steps.scan.vuln_count}} vulns"},
        }
        await run_agent_step(run, db_session, mock_services, phase_config)

        assert adapter.generate.call_args[0][0] == "Fix 3 vulns"

    async def test_custom_role_passed_to_resolver(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-as5", project_slug="as5", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-as5")
        db_session.add(run)
        await db_session.commit()

        adapter = MagicMock()
        adapter.provider_name = "agent/claude"
        adapter.generate = AsyncMock(return_value="reviewed")
        mock_services.role_resolver.resolve = AsyncMock(
            return_value=_make_resolved(adapter, role="reviewer")
        )

        phase_config = {
            "phase_name": "review",
            "kind": "agent",
            "role": "reviewer",
            "params": {"prompt": "review"},
        }
        result = await run_agent_step(run, db_session, mock_services, phase_config)

        # Verify resolve was called with role="reviewer"
        call = mock_services.role_resolver.resolve.call_args
        assert call[0][0] == "reviewer"  # first positional arg
        assert result["role"] == "reviewer"

    async def test_kwargs_passed_through(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-as6", project_slug="as6", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-as6")
        db_session.add(run)
        await db_session.commit()

        adapter = MagicMock()
        adapter.provider_name = "agent/claude"
        adapter.generate = AsyncMock(return_value="ok")
        mock_services.role_resolver.resolve = AsyncMock(return_value=_make_resolved(adapter))

        phase_config = {
            "phase_name": "x",
            "kind": "agent",
            "cli_flags": {"--foo": "bar"},
            "environment_vars": {"DEBUG": "1"},
            "timeout_seconds": 30,
            "params": {"prompt": "go", "session_id": "abc", "new_session": True},
        }
        await run_agent_step(run, db_session, mock_services, phase_config)

        kwargs = adapter.generate.call_args.kwargs
        assert kwargs.get("cli_flags") == {"--foo": "bar"}
        assert kwargs.get("environment_vars") == {"DEBUG": "1"}
        assert kwargs.get("timeout") == 30
        assert kwargs.get("session_id") == "abc"
        assert kwargs.get("new_session") is True

    async def test_task_mode_requires_workspace_path(
        self, db_session, mock_services, make_task_run
    ):
        project = ProjectConfig(
            project_id="proj-as7", project_slug="as7", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        # Explicit empty workspace_path — task mode should refuse
        run = make_task_run(project_id="proj-as7", workspace_path="")
        db_session.add(run)
        await db_session.commit()

        adapter = MagicMock()
        adapter.provider_name = "agent/claude"
        adapter.run_task = AsyncMock(return_value={"exit_code": 0})
        mock_services.role_resolver.resolve = AsyncMock(return_value=_make_resolved(adapter))

        phase_config = {
            "phase_name": "implement",
            "kind": "agent",
            "params": {"prompt": "do something", "mode": "task"},
        }
        with pytest.raises(ValueError, match="workspace_path"):
            await run_agent_step(run, db_session, mock_services, phase_config)

        adapter.run_task.assert_not_called()
