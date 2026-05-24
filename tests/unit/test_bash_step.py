# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.worker.steps.bash_step.run_bash_step."""

from unittest.mock import AsyncMock

import pytest

from backend.models import PhaseExecution, ProjectConfig
from backend.worker.steps.bash_step import run_bash_step


class TestBashStep:
    async def test_runs_command_and_captures_output(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-bs1", project_slug="bs1", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs1")
        db_session.add(run)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("hello\n", "", 0))

        phase_config = {"kind": "bash", "params": {"command": "echo hello"}}
        result = await run_bash_step(
            run, db_session, mock_services, phase_config, executor=executor
        )

        assert result["exit_code"] == 0
        assert result["stdout"] == "hello\n"
        assert result["command"] == "echo hello"
        executor.run_command.assert_awaited_once_with("echo hello", timeout=600)

    async def test_substitutes_previous_step_output(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-bs2", project_slug="bs2", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs2")
        db_session.add(run)
        await db_session.commit()

        prior = PhaseExecution(
            run_id=run.id,
            phase_name="build",
            order_index=1,
            status="completed",
            result={"artifact_path": "/tmp/build.tar"},
        )
        db_session.add(prior)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("ok", "", 0))

        phase_config = {
            "kind": "bash",
            "params": {"command": "deploy {{steps.build.artifact_path}}"},
        }
        await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)

        executor.run_command.assert_awaited_once()
        assert executor.run_command.call_args[0][0] == "deploy /tmp/build.tar"

    async def test_substitutes_run_title(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-bs-t", project_slug="bst", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs-t", title="Add login form")
        db_session.add(run)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("", "", 0))

        phase_config = {"params": {"command": "echo '{{run.title}}'"}}
        await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)

        assert "Add login form" in executor.run_command.call_args[0][0]

    async def test_raises_on_nonzero_when_failure_mode_fail(
        self, db_session, mock_services, make_task_run
    ):
        project = ProjectConfig(
            project_id="proj-bs3", project_slug="bs3", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs3")
        db_session.add(run)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("", "boom", 1))

        phase_config = {"params": {"command": "false"}, "failure_mode": "fail"}
        with pytest.raises(RuntimeError, match="bash step failed"):
            await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)

    async def test_returns_result_when_failure_mode_skip(
        self, db_session, mock_services, make_task_run
    ):
        project = ProjectConfig(
            project_id="proj-bs4", project_slug="bs4", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs4")
        db_session.add(run)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("", "boom", 1))

        phase_config = {"params": {"command": "false"}, "failure_mode": "skip"}
        result = await run_bash_step(
            run, db_session, mock_services, phase_config, executor=executor
        )

        assert result["exit_code"] == 1
        assert result["skipped"] is True

    async def test_custom_timeout(self, db_session, mock_services, make_task_run):
        project = ProjectConfig(
            project_id="proj-bs5", project_slug="bs5", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs5")
        db_session.add(run)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("", "", 0))

        phase_config = {"params": {"command": "sleep 1"}, "timeout_seconds": 30}
        await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)

        executor.run_command.assert_awaited_once_with("sleep 1", timeout=30)

    async def test_run_as_wraps_command_with_runuser(
        self, db_session, mock_services, make_task_run
    ):
        """Step ``params.run_as`` wraps the rendered command in ``runuser -l``."""
        project = ProjectConfig(
            project_id="proj-bs-ra", project_slug="bsra", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs-ra")
        db_session.add(run)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("", "", 0))
        executor.username = "root"

        phase_config = {"params": {"command": "echo hi", "run_as": "domas"}}
        await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)

        executed = executor.run_command.call_args[0][0]
        assert executed.startswith("runuser -l domas -c ")
        assert "echo hi" in executed

    async def test_project_worker_user_override_used_when_no_step_run_as(
        self, db_session, mock_services, make_task_run
    ):
        """Falls back to ``ProjectConfig.worker_user_override`` when step omits ``run_as``."""
        project = ProjectConfig(
            project_id="proj-bs-pwu",
            project_slug="bspwu",
            repo_owner="o",
            repo_name="r",
            worker_user_override="developer",
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs-pwu")
        db_session.add(run)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("", "", 0))
        executor.username = "root"

        phase_config = {"params": {"command": "id"}}
        await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)

        executed = executor.run_command.call_args[0][0]
        assert "runuser -l developer -c" in executed

    async def test_no_wrap_when_executor_already_target_user(
        self, db_session, mock_services, make_task_run
    ):
        """Skip wrapping when executor already runs as the requested user."""
        project = ProjectConfig(
            project_id="proj-bs-eq", project_slug="bseq", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs-eq")
        db_session.add(run)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("", "", 0))
        executor.username = "domas"

        phase_config = {"params": {"command": "echo hi", "run_as": "domas"}}
        await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)

        assert executor.run_command.call_args[0][0] == "echo hi"

    async def test_no_wrap_when_executor_non_root(self, db_session, mock_services, make_task_run):
        """Skip wrapping when executor isn't root — ``runuser`` would fail anyway."""
        project = ProjectConfig(
            project_id="proj-bs-nr", project_slug="bsnr", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-bs-nr")
        db_session.add(run)
        await db_session.commit()

        executor = AsyncMock()
        executor.run_command = AsyncMock(return_value=("", "", 0))
        executor.username = "deploy"

        phase_config = {"params": {"command": "echo hi", "run_as": "other"}}
        await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)

        # Command stays unwrapped — let the OS surface a clear error if
        # the deploy user happens to have passwordless sudo to ``other``.
        assert executor.run_command.call_args[0][0] == "echo hi"
