# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""End-to-end integration test for the composable step workflow model.

Drives the pipeline directly with a workflow template that mixes ``bash`` and
``agent`` step kinds. External surfaces (SSH executor for bash, AgentResolver +
adapter for agent) are mocked; the step runners themselves and the pipeline
dispatcher are exercised for real so we prove the whole composition stack
works together.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.models import PhaseExecution, TaskRun
from backend.services.agent_resolver import ResolvedAgent
from backend.services.container import ServiceContainer
from backend.worker.pipeline import execute_pipeline


def _mock_broadcaster() -> MagicMock:
    """A broadcaster stub that swallows ``log``/``event`` calls during pipeline runs."""
    return MagicMock(log=AsyncMock(), event=AsyncMock())


def _build_services_with_adapter(adapter: MagicMock) -> ServiceContainer:
    """Build a ServiceContainer whose agent_resolver returns the given adapter."""
    resolved = ResolvedAgent(adapter=adapter, agent_settings=None)

    services = MagicMock(spec=ServiceContainer)
    services.agent_resolver = MagicMock()
    services.agent_resolver.resolve_agent = AsyncMock(return_value=resolved)
    services.task_source_updater = None
    services.webhook_callbacks = None
    return services


async def _create_project(client, project_id: str) -> None:
    """POST a minimal project. The conftest autouse fixture stubs the branch lookup."""
    payload = {
        "project_id": project_id,
        "project_slug": project_id,
        "repo_owner": "o",
        "repo_name": "r",
        "default_branch": "main",
        "task_source": "manual",
        "git_provider": "github",
    }
    resp = await client.post("/api/projects", json=payload)
    assert resp.status_code == 201, resp.text


async def _create_template(client, phases: list[dict]) -> int:
    """POST a workflow template and return its id."""
    payload = {
        "name": f"composable-test-{phases[0]['phase_name']}",
        "description": "integration test template",
        "label_rules": [],
        "phases": phases,
        "is_default": False,
        "is_system": False,
    }
    resp = await client.post("/api/workflow-templates", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _create_run(client, project_id: str, template_id: int, title: str) -> int:
    """POST a TaskRun bound to the given workflow template, return the run id."""
    payload = {
        "project_id": project_id,
        "title": title,
        "description": "demo run",
        "workflow_template_id": template_id,
    }
    resp = await client.post("/api/runs", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _load_run(db_session, run_id: int) -> TaskRun:
    result = await db_session.execute(select(TaskRun).where(TaskRun.id == run_id))
    return result.scalar_one()


async def _load_phases(db_session, run_id: int) -> list[PhaseExecution]:
    result = await db_session.execute(
        select(PhaseExecution)
        .where(PhaseExecution.run_id == run_id)
        .order_by(PhaseExecution.order_index)
    )
    return list(result.scalars().all())


@pytest.mark.usefixtures("mock_get_default_branch")
class TestComposableWorkflow:
    """Run the pipeline against a real bash+agent workflow template end-to-end."""

    async def test_bash_then_agent_runs_in_order(self, client, db_session):
        """Mixed bash + agent template: both runners fire, results land in PhaseExecution."""
        project_id = "proj-comp-1"
        await _create_project(client, project_id)
        template_id = await _create_template(
            client,
            phases=[
                {
                    "phase_name": "echo-step",
                    "kind": "bash",
                    "params": {"command": "echo title is {{run.title}}"},
                },
                {
                    "phase_name": "ask-agent",
                    "kind": "agent",
                    "role": "coder",
                    "params": {"prompt": "what about {{run.title}}?"},
                },
            ],
        )
        run_id = await _create_run(client, project_id, template_id, "Hello composable")
        run = await _load_run(db_session, run_id)

        fake_executor = AsyncMock()
        fake_executor.run_command = AsyncMock(return_value=("title is Hello composable\n", "", 0))

        adapter = MagicMock()
        adapter.provider_name = "agent/claude"
        adapter.generate = AsyncMock(return_value="Looks fine.")

        services = _build_services_with_adapter(adapter)

        with (
            patch(
                "backend.worker.steps.bash_step.get_ssh_for_run",
                new=AsyncMock(return_value=fake_executor),
            ),
            patch("backend.worker.pipeline.broadcaster", new=_mock_broadcaster()),
        ):
            await execute_pipeline(run, db_session, services)

        await db_session.refresh(run)
        assert run.status == "completed"

        phases = await _load_phases(db_session, run_id)
        assert len(phases) == 2

        bash_pe, agent_pe = phases

        assert bash_pe.phase_name == "echo-step"
        assert bash_pe.status == "completed"
        assert bash_pe.phase_config is not None
        assert bash_pe.phase_config["kind"] == "bash"
        assert bash_pe.result is not None
        assert bash_pe.result["exit_code"] == 0
        assert "Hello composable" in bash_pe.result["stdout"]
        assert bash_pe.result["command"] == "echo title is Hello composable"

        assert agent_pe.phase_name == "ask-agent"
        assert agent_pe.status == "completed"
        assert agent_pe.phase_config is not None
        assert agent_pe.phase_config["kind"] == "agent"
        assert agent_pe.result is not None
        assert agent_pe.result["provider"] == "agent/claude"
        assert agent_pe.result["response"] == "Looks fine."
        assert agent_pe.result["prompt"] == "what about Hello composable?"

        fake_executor.run_command.assert_awaited_once()
        adapter.generate.assert_awaited_once()

    async def test_step_output_flows_to_next_step(self, client, db_session):
        """A bash step writes ``stdout``; the next bash step's command renders it via templating."""
        project_id = "proj-comp-2"
        await _create_project(client, project_id)
        template_id = await _create_template(
            client,
            phases=[
                {
                    "phase_name": "compute",
                    "kind": "bash",
                    "params": {"command": "printf 42"},
                },
                {
                    "phase_name": "consume",
                    "kind": "bash",
                    "params": {"command": "echo got {{steps.compute.stdout}}"},
                },
            ],
        )
        run_id = await _create_run(client, project_id, template_id, "flow test")
        run = await _load_run(db_session, run_id)

        fake_executor = AsyncMock()
        # First call: compute → stdout='42'. Second call: consume → succeeds.
        fake_executor.run_command = AsyncMock(
            side_effect=[
                ("42", "", 0),
                ("got 42\n", "", 0),
            ]
        )

        services = _build_services_with_adapter(MagicMock())

        with (
            patch(
                "backend.worker.steps.bash_step.get_ssh_for_run",
                new=AsyncMock(return_value=fake_executor),
            ),
            patch("backend.worker.pipeline.broadcaster", new=_mock_broadcaster()),
        ):
            await execute_pipeline(run, db_session, services)

        await db_session.refresh(run)
        assert run.status == "completed"

        phases = await _load_phases(db_session, run_id)
        assert len(phases) == 2
        compute_pe, consume_pe = phases

        assert compute_pe.phase_name == "compute"
        assert compute_pe.status == "completed"
        assert compute_pe.result is not None
        assert compute_pe.result["stdout"] == "42"

        assert consume_pe.phase_name == "consume"
        assert consume_pe.status == "completed"
        assert consume_pe.result is not None
        # Crucial assertion: the rendered command in the persisted result shows
        # the previous step's stdout was substituted in.
        assert consume_pe.result["command"] == "echo got 42"

        # And the executor actually received the rendered command, proving the
        # templating ran before dispatch (not just on the read path).
        assert fake_executor.run_command.await_count == 2
        first_call_cmd = fake_executor.run_command.await_args_list[0].args[0]
        second_call_cmd = fake_executor.run_command.await_args_list[1].args[0]
        assert first_call_cmd == "printf 42"
        assert second_call_cmd == "echo got 42"
