# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for event-driven pipeline execution."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.models import ProjectConfig
from backend.repositories.phase_execution_repo import PhaseExecutionRepository
from backend.worker.pipeline import execute_pipeline

_ALL_PHASE_NAMES = [
    "workspace_setup",
    "init",
    "planning",
    "coding",
    "testing",
    "reviewing",
    "approval",
    "finalization",
    "pr_fetch",
    "task_creation",
]


def _mock_broadcaster():
    return MagicMock(log=AsyncMock(), event=AsyncMock())


def _make_phase_modules():
    """Build a dict of {phase_name: mock_module} for all known phases."""
    modules = {}
    for name in _ALL_PHASE_NAMES:
        mod = MagicMock()
        mod.run = AsyncMock(return_value=None)
        modules[name] = mod
    return modules


def _pipeline_patches(modules: dict):
    """Return a combined context-manager that patches _phase_modules + broadcaster."""
    return (
        patch("backend.worker.pipeline._phase_modules", modules),
        patch("backend.worker.pipeline.broadcaster", new=_mock_broadcaster()),
    )


class TestExecutePipeline:
    async def test_runs_all_auto_phases(self, db_session, make_task_run, mock_services):
        """All phases with trigger_mode=auto complete in sequence."""
        project = ProjectConfig(
            project_id="proj-pipe", project_slug="pipe", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-pipe")
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        mods = _make_phase_modules()
        p1, p2 = _pipeline_patches(mods)
        with p1, p2:
            await execute_pipeline(run, db_session, mock_services)

            assert run.status == "completed"
            assert run.completed_at is not None
            mods["workspace_setup"].run.assert_called_once()
            mods["finalization"].run.assert_called_once()

        # Verify PhaseExecution rows were created and all completed
        repo = PhaseExecutionRepository(db_session)
        phases = await repo.get_by_run(run.id)
        assert len(phases) == 8
        assert all(p.status == "completed" for p in phases)

    async def test_stops_at_wait_for_trigger(self, db_session, make_task_run, mock_services):
        """Phase with trigger_mode=wait_for_trigger parks the run."""
        project = ProjectConfig(
            project_id="proj-trig", project_slug="trig", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-trig")
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        repo = PhaseExecutionRepository(db_session)
        await repo.create_for_run(
            run.id,
            [
                {"phase_name": "workspace_setup", "trigger_mode": "auto"},
                {"phase_name": "init", "trigger_mode": "wait_for_trigger"},
                {"phase_name": "planning", "trigger_mode": "auto"},
            ],
        )
        await db_session.commit()

        mods = _make_phase_modules()
        p1, p2 = _pipeline_patches(mods)
        with p1, p2:
            await execute_pipeline(run, db_session, mock_services)

            assert run.status == "waiting_for_trigger"
            mods["workspace_setup"].run.assert_called_once()
            mods["init"].run.assert_not_called()

    async def test_stops_at_wait_for_approval(self, db_session, make_task_run, mock_services):
        """Approval phase with trigger_mode=wait_for_approval parks the run after execution."""
        project = ProjectConfig(
            project_id="proj-appr", project_slug="appr", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-appr")
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        repo = PhaseExecutionRepository(db_session)
        await repo.create_for_run(
            run.id,
            [
                {"phase_name": "workspace_setup", "trigger_mode": "auto"},
                {"phase_name": "approval", "trigger_mode": "wait_for_approval"},
                {"phase_name": "finalization", "trigger_mode": "auto"},
            ],
        )
        await db_session.commit()

        mods = _make_phase_modules()
        p1, p2 = _pipeline_patches(mods)
        with p1, p2:
            await execute_pipeline(run, db_session, mock_services)

            assert run.status == "awaiting_approval"
            mods["workspace_setup"].run.assert_called_once()
            mods["approval"].run.assert_called_once()
            mods["finalization"].run.assert_not_called()

    async def test_resume_from_waiting(self, db_session, make_task_run, mock_services):
        """After advancing a waiting phase, pipeline continues from next pending."""
        project = ProjectConfig(
            project_id="proj-resume", project_slug="resume", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-resume")
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        repo = PhaseExecutionRepository(db_session)
        phases = await repo.create_for_run(
            run.id,
            [
                {"phase_name": "workspace_setup", "trigger_mode": "auto"},
                {"phase_name": "init", "trigger_mode": "auto"},
            ],
        )
        await repo.update_status(phases[0], "completed")
        await db_session.commit()

        mods = _make_phase_modules()
        p1, p2 = _pipeline_patches(mods)
        with p1, p2:
            await execute_pipeline(run, db_session, mock_services)

            mods["workspace_setup"].run.assert_not_called()
            mods["init"].run.assert_called_once()

    async def test_phase_failure_retry(self, db_session, make_task_run, mock_services):
        """Failed phase retries up to max_retries, then succeeds."""
        project = ProjectConfig(
            project_id="proj-retry", project_slug="retry", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-retry")
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        repo = PhaseExecutionRepository(db_session)
        await repo.create_for_run(
            run.id,
            [
                {"phase_name": "workspace_setup", "trigger_mode": "auto", "max_retries": 3},
            ],
        )
        await db_session.commit()

        call_count = 0

        async def _flaky_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")

        mods = _make_phase_modules()
        mods["workspace_setup"].run = _flaky_run
        p1, p2 = _pipeline_patches(mods)
        with p1, p2:
            await execute_pipeline(run, db_session, mock_services)

            assert run.status == "completed"
            assert call_count == 3

    async def test_phase_failure_exhausted(self, db_session, make_task_run, mock_services):
        """Phase that exhausts retries parks the run as failed."""
        project = ProjectConfig(
            project_id="proj-exhaust", project_slug="exhaust", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-exhaust")
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        repo = PhaseExecutionRepository(db_session)
        await repo.create_for_run(
            run.id,
            [
                {"phase_name": "workspace_setup", "trigger_mode": "auto", "max_retries": 2},
            ],
        )
        await db_session.commit()

        mods = _make_phase_modules()
        mods["workspace_setup"].run = AsyncMock(side_effect=RuntimeError("permanent failure"))
        p1, p2 = _pipeline_patches(mods)
        with p1, p2:
            await execute_pipeline(run, db_session, mock_services)

            assert run.status == "failed"
            assert "permanent failure" in run.error_message

        phases = await repo.get_by_run(run.id)
        assert phases[0].status == "failed"
        assert phases[0].retry_count == 2

    async def test_handles_cancelled_status(self, db_session, make_task_run, mock_services):
        """Pipeline exits if run is cancelled externally."""
        project = ProjectConfig(
            project_id="proj-cancel", project_slug="cancel", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-cancel")
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        repo = PhaseExecutionRepository(db_session)
        await repo.create_for_run(
            run.id,
            [
                {"phase_name": "workspace_setup", "trigger_mode": "auto"},
                {"phase_name": "init", "trigger_mode": "auto"},
            ],
        )
        await db_session.commit()

        async def _cancel_after_ws(*args, **kwargs):
            run.status = "cancelled"
            await db_session.commit()

        mods = _make_phase_modules()
        mods["workspace_setup"].run = _cancel_after_ws
        p1, p2 = _pipeline_patches(mods)
        with p1, p2:
            await execute_pipeline(run, db_session, mock_services)

            mods["init"].run.assert_not_called()