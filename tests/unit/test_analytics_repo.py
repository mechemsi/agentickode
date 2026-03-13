# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for AnalyticsRepository."""

from datetime import datetime, timedelta

import pytest

from backend.models import AgentInvocation, PhaseExecution, ProjectConfig, TaskRun
from backend.repositories.analytics_repo import AnalyticsRepository


def _make_project(session):
    proj = ProjectConfig(
        project_id="proj-1",
        project_slug="proj",
        repo_owner="org",
        repo_name="repo",
        default_branch="main",
    )
    session.add(proj)
    return proj


def _make_run(session, status="completed", started_at=None, completed_at=None, **kw):
    now = datetime.utcnow()
    defaults = dict(
        task_id="TASK-1",
        project_id="proj-1",
        title="Test",
        description="",
        branch_name="feature/test",
        workspace_path="/ws",
        repo_owner="org",
        repo_name="repo",
        status=status,
        started_at=started_at or now - timedelta(minutes=10),
        completed_at=completed_at or now,
        created_at=now,
    )
    defaults.update(kw)
    run = TaskRun(**defaults)
    session.add(run)
    return run


@pytest.mark.asyncio
async def test_empty_summary(db_session):
    """Empty DB returns zero-value summary."""
    repo = AnalyticsRepository(db_session)
    summary = await repo.get_summary(days=14)
    assert summary["total_runs"] == 0
    assert summary["success_rate"] == 0.0
    assert summary["avg_duration_seconds"] == 0.0
    assert summary["avg_phase_durations"] == []
    assert summary["agent_stats"] == []
    assert summary["runs_over_time"] == []


@pytest.mark.asyncio
async def test_success_rate_calculation(db_session):
    """Success rate = completed / (completed + failed) * 100."""
    _make_project(db_session)
    _make_run(db_session, status="completed")
    _make_run(db_session, status="completed")
    _make_run(db_session, status="failed")
    await db_session.flush()

    repo = AnalyticsRepository(db_session)
    summary = await repo.get_summary(days=14)
    assert summary["total_runs"] == 3
    # 2 completed, 1 failed → 66.7%
    assert summary["success_rate"] == pytest.approx(66.7, abs=0.1)


@pytest.mark.asyncio
async def test_avg_duration(db_session):
    """Average duration computed from started_at/completed_at."""
    _make_project(db_session)
    now = datetime.utcnow()
    # Run 1: 120 seconds
    _make_run(
        db_session,
        status="completed",
        started_at=now - timedelta(seconds=120),
        completed_at=now,
    )
    # Run 2: 60 seconds
    _make_run(
        db_session,
        status="completed",
        started_at=now - timedelta(seconds=60),
        completed_at=now,
    )
    await db_session.flush()

    repo = AnalyticsRepository(db_session)
    summary = await repo.get_summary(days=14)
    # avg = (120 + 60) / 2 = 90
    assert summary["avg_duration_seconds"] == pytest.approx(90.0, abs=1)


@pytest.mark.asyncio
async def test_phase_durations(db_session):
    """Phase durations grouped by phase_name."""
    _make_project(db_session)
    run = _make_run(db_session, status="completed")
    await db_session.flush()

    now = datetime.utcnow()
    db_session.add(
        PhaseExecution(
            run_id=run.id,
            phase_name="coding",
            order_index=0,
            status="completed",
            started_at=now - timedelta(seconds=30),
            completed_at=now,
            created_at=now,
        )
    )
    await db_session.flush()

    repo = AnalyticsRepository(db_session)
    summary = await repo.get_summary(days=14)
    phases = summary["avg_phase_durations"]
    assert len(phases) == 1
    assert phases[0]["phase_name"] == "coding"
    assert phases[0]["avg_seconds"] == pytest.approx(30.0, abs=1)
    assert phases[0]["count"] == 1


@pytest.mark.asyncio
async def test_agent_stats(db_session):
    """Agent stats with success rate and avg duration."""
    _make_project(db_session)
    run = _make_run(db_session, status="completed")
    await db_session.flush()

    now = datetime.utcnow()
    db_session.add(
        AgentInvocation(
            run_id=run.id,
            agent_name="claude",
            status="success",
            duration_seconds=10.0,
            started_at=now - timedelta(seconds=10),
            completed_at=now,
        )
    )
    db_session.add(
        AgentInvocation(
            run_id=run.id,
            agent_name="claude",
            status="failed",
            duration_seconds=5.0,
            started_at=now - timedelta(seconds=5),
            completed_at=now,
        )
    )
    await db_session.flush()

    repo = AnalyticsRepository(db_session)
    summary = await repo.get_summary(days=14)
    agents = summary["agent_stats"]
    assert len(agents) == 1
    assert agents[0]["agent_name"] == "claude"
    assert agents[0]["total_runs"] == 2
    assert agents[0]["success_rate"] == 50.0
    assert agents[0]["avg_duration_seconds"] == pytest.approx(7.5, abs=0.1)


@pytest.mark.asyncio
async def test_runs_over_time(db_session):
    """Runs grouped by date."""
    _make_project(db_session)
    now = datetime.utcnow()
    _make_run(db_session, status="completed", created_at=now)
    _make_run(db_session, status="pending", created_at=now - timedelta(days=1))
    await db_session.flush()

    repo = AnalyticsRepository(db_session)
    summary = await repo.get_summary(days=14)
    assert len(summary["runs_over_time"]) >= 1
