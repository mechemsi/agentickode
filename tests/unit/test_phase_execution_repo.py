# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for PhaseExecutionRepository."""

from backend.models import ProjectConfig
from backend.repositories.phase_execution_repo import PhaseExecutionRepository


class TestPhaseExecutionRepo:
    async def test_create_for_run(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-pe", project_slug="pe", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-pe")
        db_session.add(run)
        await db_session.commit()

        repo = PhaseExecutionRepository(db_session)
        phases = [
            {"phase_name": "workspace_setup", "trigger_mode": "auto"},
            {"phase_name": "approval", "trigger_mode": "wait_for_approval"},
        ]
        result = await repo.create_for_run(run.id, phases)

        assert len(result) == 2
        assert result[0].phase_name == "workspace_setup"
        assert result[0].order_index == 0
        assert result[0].trigger_mode == "auto"
        assert result[1].phase_name == "approval"
        assert result[1].trigger_mode == "wait_for_approval"

    async def test_create_for_run_preserves_step_kind(self, db_session, make_task_run):
        """phase_config dict is stored verbatim — the `kind` discriminator
        added in Task 1.1 must round-trip so the pipeline dispatcher
        (Task 1.5) can branch on it."""
        project = ProjectConfig(
            project_id="proj-pe-kind", project_slug="pek", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-pe-kind")
        db_session.add(run)
        await db_session.commit()

        repo = PhaseExecutionRepository(db_session)
        phases = [
            {"phase_name": "build", "kind": "bash", "params": {"command": "make build"}},
            {"phase_name": "fix", "kind": "agent", "params": {"prompt": "fix it"}},
            {"phase_name": "planning"},  # no kind → legacy default semantics
        ]
        result = await repo.create_for_run(run.id, phases)
        await db_session.commit()

        assert result[0].phase_config["kind"] == "bash"
        assert result[0].phase_config["params"]["command"] == "make build"
        assert result[1].phase_config["kind"] == "agent"
        assert result[2].phase_config.get("kind") is None  # legacy template, dispatch defaults

    async def test_get_by_run(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-pe2", project_slug="pe2", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-pe2")
        db_session.add(run)
        await db_session.commit()

        repo = PhaseExecutionRepository(db_session)
        await repo.create_for_run(
            run.id,
            [
                {"phase_name": "init"},
                {"phase_name": "planning"},
            ],
        )
        await db_session.commit()

        phases = await repo.get_by_run(run.id)
        assert len(phases) == 2
        assert phases[0].phase_name == "init"
        assert phases[1].phase_name == "planning"

    async def test_get_by_run_and_phase(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-pe3", project_slug="pe3", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-pe3")
        db_session.add(run)
        await db_session.commit()

        repo = PhaseExecutionRepository(db_session)
        await repo.create_for_run(run.id, [{"phase_name": "coding"}])
        await db_session.commit()

        pe = await repo.get_by_run_and_phase(run.id, "coding")
        assert pe is not None
        assert pe.phase_name == "coding"

        missing = await repo.get_by_run_and_phase(run.id, "nonexistent")
        assert missing is None

    async def test_get_next_pending(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-pe4", project_slug="pe4", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-pe4")
        db_session.add(run)
        await db_session.commit()

        repo = PhaseExecutionRepository(db_session)
        phases = await repo.create_for_run(
            run.id,
            [
                {"phase_name": "workspace_setup"},
                {"phase_name": "init"},
            ],
        )
        await db_session.commit()

        # First pending should be workspace_setup
        nxt = await repo.get_next_pending(run.id)
        assert nxt is not None
        assert nxt.phase_name == "workspace_setup"

        # Mark first as completed, next pending should be init
        await repo.update_status(phases[0], "completed")
        await db_session.commit()
        nxt = await repo.get_next_pending(run.id)
        assert nxt is not None
        assert nxt.phase_name == "init"

        # Mark second as completed, no more pending
        await repo.update_status(phases[1], "completed")
        await db_session.commit()
        nxt = await repo.get_next_pending(run.id)
        assert nxt is None

    async def test_update_status_sets_timestamps(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-pe5", project_slug="pe5", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-pe5")
        db_session.add(run)
        await db_session.commit()

        repo = PhaseExecutionRepository(db_session)
        phases = await repo.create_for_run(run.id, [{"phase_name": "coding"}])
        await db_session.commit()

        pe = phases[0]
        assert pe.started_at is None

        await repo.update_status(pe, "running")
        assert pe.started_at is not None
        assert pe.completed_at is None

        await repo.update_status(pe, "completed", result={"ok": True})
        assert pe.completed_at is not None
        assert pe.result == {"ok": True}
