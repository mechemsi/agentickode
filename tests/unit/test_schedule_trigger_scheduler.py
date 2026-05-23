# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.worker.schedule_trigger_scheduler.ScheduleTriggerScheduler."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.models import ProjectConfig, TaskRun, WorkflowTemplate
from backend.worker.schedule_trigger_scheduler import ScheduleTriggerScheduler


def _make_scheduler(db_engine) -> ScheduleTriggerScheduler:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    return ScheduleTriggerScheduler(factory, poll_seconds=30)


async def _add_project(db_session, project_id: str = "sched-proj") -> ProjectConfig:
    project = ProjectConfig(
        project_id=project_id,
        project_slug=project_id,
        repo_owner="org",
        repo_name="repo",
        default_branch="main",
        task_source="schedule",
        git_provider="gitea",
        workspace_path="/workspaces/sched",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _add_template(
    db_session,
    *,
    name: str,
    triggers: list[dict],
) -> WorkflowTemplate:
    tpl = WorkflowTemplate(
        name=name,
        description="",
        label_rules=[],
        triggers=triggers,
        phases=[{"phase_name": "init", "enabled": True}],
    )
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)
    return tpl


class TestIsDue:
    def test_first_observation_arms_the_trigger(self, db_engine):
        sched = _make_scheduler(db_engine)
        now = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
        # First call primes _last_fired without firing.
        # The cron next-occurrence from primed timestamp must be <= now for fire.
        # Use a 'every minute' cron so primed time + 1min is past 'now'.
        is_due = sched._is_due(1, "* * * * *", now)
        assert is_due is True
        # State stored
        assert (1, "* * * * *") in sched._last_fired

    def test_not_due_when_next_occurrence_in_future(self, db_engine):
        sched = _make_scheduler(db_engine)
        # Prime artificially in the past so the first call would fire
        key = (1, "0 * * * *")
        # Set last_fired to right after the most recent hour boundary so
        # the next occurrence is an hour out.
        now = datetime(2026, 5, 24, 12, 30, tzinfo=UTC)
        sched._last_fired[key] = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        # next after 12:00 = 13:00, which is > 12:30 -> not due
        assert sched._is_due(1, "0 * * * *", now) is False

    def test_due_when_next_occurrence_elapsed(self, db_engine):
        sched = _make_scheduler(db_engine)
        key = (2, "0 * * * *")
        # Prime last fired well before now so 0 * * * * fires
        sched._last_fired[key] = datetime(2026, 5, 24, 11, 0, tzinfo=UTC)
        now = datetime(2026, 5, 24, 12, 30, tzinfo=UTC)
        # next after 11:00 = 12:00, which is <= 12:30 -> due
        assert sched._is_due(2, "0 * * * *", now) is True
        assert sched._last_fired[key] == now

    def test_invalid_cron_returns_false(self, db_engine):
        sched = _make_scheduler(db_engine)
        sched._last_fired[(3, "not-a-cron")] = datetime(2026, 5, 24, tzinfo=UTC) - timedelta(
            hours=1
        )
        assert sched._is_due(3, "not-a-cron", datetime(2026, 5, 24, tzinfo=UTC)) is False

    def test_does_not_double_fire_within_window(self, db_engine):
        sched = _make_scheduler(db_engine)
        now = datetime(2026, 5, 24, 12, 30, tzinfo=UTC)
        key = (4, "* * * * *")
        sched._last_fired[key] = now - timedelta(minutes=5)
        first = sched._is_due(4, "* * * * *", now)
        second = sched._is_due(4, "* * * * *", now)
        assert first is True
        assert second is False  # already fired at `now`


class TestTickDispatches:
    async def test_tick_creates_run_for_due_schedule(self, db_session, db_engine):
        project = await _add_project(db_session)
        template = await _add_template(
            db_session,
            name="hourly",
            triggers=[
                {
                    "type": "schedule",
                    "cron": "* * * * *",  # every minute
                    "project_id": project.project_id,
                }
            ],
        )

        sched = _make_scheduler(db_engine)
        # Arm last_fired well in the past so the first call's _is_due fires.
        sched._last_fired[(template.id, "* * * * *")] = datetime(2026, 1, 1, tzinfo=UTC)

        await sched._tick()

        runs = (await db_session.execute(select(TaskRun))).scalars().all()
        assert len(runs) == 1
        run = runs[0]
        assert run.task_source == "schedule"
        assert run.workflow_template_id == template.id
        assert run.task_source_meta["schedule_cron"] == "* * * * *"
        assert run.task_source_meta["workflow_template_name"] == "hourly"

    async def test_tick_skips_template_without_project_id(self, db_session, db_engine):
        await _add_template(
            db_session,
            name="orphan",
            triggers=[{"type": "schedule", "cron": "* * * * *"}],
        )
        sched = _make_scheduler(db_engine)
        sched._last_fired[(1, "* * * * *")] = datetime(2026, 1, 1, tzinfo=UTC)
        await sched._tick()
        runs = (await db_session.execute(select(TaskRun))).scalars().all()
        assert runs == []

    async def test_tick_skips_template_with_unknown_project(self, db_session, db_engine):
        template = await _add_template(
            db_session,
            name="bad-proj",
            triggers=[{"type": "schedule", "cron": "* * * * *", "project_id": "does-not-exist"}],
        )
        sched = _make_scheduler(db_engine)
        sched._last_fired[(template.id, "* * * * *")] = datetime(2026, 1, 1, tzinfo=UTC)
        await sched._tick()
        runs = (await db_session.execute(select(TaskRun))).scalars().all()
        assert runs == []

    async def test_tick_only_processes_schedule_triggers(self, db_session, db_engine):
        await _add_project(db_session)
        await _add_template(
            db_session,
            name="label-only",
            triggers=[{"type": "label", "match_any": ["x"]}],
        )
        sched = _make_scheduler(db_engine)
        await sched._tick()
        runs = (await db_session.execute(select(TaskRun))).scalars().all()
        assert runs == []


class TestStopRun:
    async def test_stop_flips_running_flag(self, db_engine):
        sched = _make_scheduler(db_engine)
        sched._running = True
        sched.stop()
        assert sched._running is False

    async def test_run_logs_started_and_exits_when_stopped(self, db_engine, monkeypatch):
        sched = _make_scheduler(db_engine)

        async def fake_sleep(_):
            # Stop the loop after the first iteration so run() returns.
            sched._running = False

        monkeypatch.setattr("backend.worker.schedule_trigger_scheduler.asyncio.sleep", fake_sleep)

        # Replace _tick with a no-op so we don't need DB state.
        async def fake_tick():
            return None

        monkeypatch.setattr(sched, "_tick", fake_tick)
        await sched.run()  # should return cleanly
        assert sched._running is False


def test_signature_smoke():
    """Documented signature: takes session_factory + optional poll_seconds."""
    factory = MagicMock()
    sched = ScheduleTriggerScheduler(factory, poll_seconds=15)
    assert sched._poll_seconds == 15
