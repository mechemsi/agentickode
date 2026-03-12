# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for WorkerEngine."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models import AppSetting, PhaseExecution, ProjectConfig
from backend.worker.engine import WorkerEngine


class TestWorkerEngine:
    async def test_dispatch_pending(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-eng1", project_slug="eng1", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-eng1", status="pending")
        db_session.add(run)
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._dispatch_pending(db_session)
            assert len(engine._active_runs) == 1

    async def test_dispatch_respects_max_concurrent(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-eng2", project_slug="eng2", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        for i in range(5):
            run = make_task_run(task_id=f"TASK-{i}", project_id="proj-eng2", status="pending")
            db_session.add(run)
        await db_session.commit()

        engine = WorkerEngine()
        engine._active_runs = {100: MagicMock(), 101: MagicMock(), 102: MagicMock()}
        for t in engine._active_runs.values():
            t.done.return_value = False

        await engine._dispatch_pending(db_session)
        assert len(engine._active_runs) == 3

    async def test_handle_waiting_approved(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-eng3", project_slug="eng3", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-eng3", status="awaiting_approval")
        run.approved = True
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        # Create a waiting PhaseExecution
        pe = PhaseExecution(
            run_id=run.id,
            phase_name="approval",
            order_index=5,
            trigger_mode="wait_for_approval",
            status="waiting",
        )
        db_session.add(pe)
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._handle_waiting(db_session)
            assert run.status == "pending"
            assert pe.status == "completed"

    async def test_handle_waiting_rejected(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-eng4", project_slug="eng4", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-eng4", status="awaiting_approval")
        run.approved = False
        run.rejection_reason = "bad code"
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        pe = PhaseExecution(
            run_id=run.id,
            phase_name="approval",
            order_index=5,
            trigger_mode="wait_for_approval",
            status="waiting",
        )
        db_session.add(pe)
        await db_session.commit()

        engine = WorkerEngine()
        with patch(
            "backend.worker.engine.broadcaster",
            new=MagicMock(log=AsyncMock(), event=AsyncMock()),
        ):
            await engine._handle_waiting(db_session)
            assert run.status == "failed"
            assert "Rejected" in run.error_message
            assert pe.status == "failed"

    async def test_handle_waiting_trigger_advanced(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-eng5", project_slug="eng5", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-eng5", status="waiting_for_trigger")
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        # Phase was advanced externally: status changed from "waiting" to "pending"
        pe = PhaseExecution(
            run_id=run.id,
            phase_name="init",
            order_index=1,
            trigger_mode="wait_for_trigger",
            status="pending",
        )
        db_session.add(pe)
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._handle_waiting(db_session)
            assert run.status == "pending"

    async def test_dispatch_skips_projects_with_active_run(self, db_session, make_task_run):
        """Pending runs for a project with an active run are not dispatched."""
        for pid, slug in [("proj-qa", "qa"), ("proj-qb", "qb")]:
            db_session.add(
                ProjectConfig(project_id=pid, project_slug=slug, repo_owner="o", repo_name="r")
            )

        # proj-qa: one running, one pending
        run_a_active = make_task_run(task_id="TASK-A1", project_id="proj-qa", status="running")
        run_a_pending = make_task_run(task_id="TASK-A2", project_id="proj-qa", status="pending")
        # proj-qb: one pending only
        run_b_pending = make_task_run(task_id="TASK-B1", project_id="proj-qb", status="pending")

        db_session.add_all([run_a_active, run_a_pending, run_b_pending])
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._dispatch_pending(db_session)

        # Only proj-qb's pending run should have been dispatched
        assert run_b_pending.id in engine._active_runs
        assert run_a_pending.id not in engine._active_runs

    async def test_dispatch_allows_after_active_completes(self, db_session, make_task_run):
        """Once the active run completes, its project's pending runs can be dispatched."""
        db_session.add(
            ProjectConfig(project_id="proj-qc", project_slug="qc", repo_owner="o", repo_name="r")
        )

        run_done = make_task_run(task_id="TASK-C1", project_id="proj-qc", status="completed")
        run_pending = make_task_run(task_id="TASK-C2", project_id="proj-qc", status="pending")
        db_session.add_all([run_done, run_pending])
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._dispatch_pending(db_session)

        assert run_pending.id in engine._active_runs

    async def test_awaiting_approval_does_not_block_project(self, db_session, make_task_run):
        """A run in awaiting_approval doesn't block — no further code changes needed."""
        db_session.add(
            ProjectConfig(project_id="proj-qd", project_slug="qd", repo_owner="o", repo_name="r")
        )

        run_awaiting = make_task_run(
            task_id="TASK-D1", project_id="proj-qd", status="awaiting_approval"
        )
        run_pending = make_task_run(task_id="TASK-D2", project_id="proj-qd", status="pending")
        db_session.add_all([run_awaiting, run_pending])
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._dispatch_pending(db_session)

        assert run_pending.id in engine._active_runs

    async def test_dispatch_one_per_project_per_tick(self, db_session, make_task_run):
        """Multiple pending runs for the same project: only the oldest is dispatched."""
        db_session.add(
            ProjectConfig(project_id="proj-qe", project_slug="qe", repo_owner="o", repo_name="r")
        )

        run1 = make_task_run(task_id="TASK-E1", project_id="proj-qe", status="pending")
        run2 = make_task_run(task_id="TASK-E2", project_id="proj-qe", status="pending")
        run3 = make_task_run(task_id="TASK-E3", project_id="proj-qe", status="pending")
        db_session.add_all([run1, run2, run3])
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._dispatch_pending(db_session)

        # Only one run dispatched despite 3 pending for the same project
        assert len(engine._active_runs) == 1
        assert run1.id in engine._active_runs

    async def test_handle_timeouts(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-eng6", project_slug="eng6", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-eng6", status="awaiting_approval")
        run.approval_requested_at = datetime.now(UTC) - timedelta(hours=25)
        db_session.add(run)
        await db_session.commit()

        engine = WorkerEngine()
        with patch(
            "backend.worker.engine.broadcaster",
            new=MagicMock(log=AsyncMock(), event=AsyncMock()),
        ):
            await engine._handle_timeouts(db_session)
            assert run.status == "timeout"

    async def test_dispatch_blocked_by_schedule(self, db_session, make_task_run):
        """Runs are blocked when outside the schedule and skip_schedule is not set."""
        project = ProjectConfig(
            project_id="proj-sched1", project_slug="sched1", repo_owner="o", repo_name="r"
        )
        db_session.add(project)

        # Store a schedule that blocks all days
        setting = AppSetting(
            key="queue_schedule",
            value={
                "enabled": True,
                "timezone": "UTC",
                "days": {},  # no days configured = all blocked
            },
        )
        db_session.add(setting)

        run = make_task_run(project_id="proj-sched1", status="pending")
        db_session.add(run)
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._dispatch_pending(db_session)
            assert len(engine._active_runs) == 0

    async def test_dispatch_skip_schedule_bypasses(self, db_session, make_task_run):
        """Runs with skip_schedule=True bypass the schedule check."""
        project = ProjectConfig(
            project_id="proj-sched2", project_slug="sched2", repo_owner="o", repo_name="r"
        )
        db_session.add(project)

        setting = AppSetting(
            key="queue_schedule",
            value={
                "enabled": True,
                "timezone": "UTC",
                "days": {},  # all blocked
            },
        )
        db_session.add(setting)

        run = make_task_run(
            project_id="proj-sched2",
            status="pending",
            task_source_meta={"skip_schedule": True},
        )
        db_session.add(run)
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._dispatch_pending(db_session)
            assert len(engine._active_runs) == 1

    async def test_dispatch_within_schedule_allows(self, db_session, make_task_run):
        """Runs dispatch normally when within the schedule window."""
        project = ProjectConfig(
            project_id="proj-sched3", project_slug="sched3", repo_owner="o", repo_name="r"
        )
        db_session.add(project)

        # Allow all days, all hours
        setting = AppSetting(
            key="queue_schedule",
            value={
                "enabled": True,
                "timezone": "UTC",
                "days": {str(i): {"start": "00:00", "end": "23:59"} for i in range(7)},
            },
        )
        db_session.add(setting)

        run = make_task_run(project_id="proj-sched3", status="pending")
        db_session.add(run)
        await db_session.commit()

        engine = WorkerEngine()
        with patch.object(engine, "_run_pipeline", new_callable=AsyncMock):
            await engine._dispatch_pending(db_session)
            assert len(engine._active_runs) == 1