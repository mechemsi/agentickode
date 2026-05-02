# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for IssuePollerScheduler."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.models import ProjectConfig
from backend.worker.issue_poller_scheduler import IssuePollerScheduler


@pytest.fixture()
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _insert_project(session_factory, **overrides) -> ProjectConfig:
    async with session_factory() as s:
        p = ProjectConfig(
            project_id=overrides.pop("project_id", "p"),
            project_slug="p",
            repo_owner="o",
            repo_name="r",
            default_branch="main",
            task_source=overrides.pop("task_source", "github"),
            git_provider="github",
            poll_enabled=overrides.pop("poll_enabled", True),
            poll_interval_minutes=overrides.pop("poll_interval_minutes", 5),
            integration_config={},
            **overrides,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p


class TestIssuePollerScheduler:
    async def test_tick_polls_only_enabled_projects(self, session_factory):
        await _insert_project(session_factory, project_id="enabled", poll_enabled=True)
        await _insert_project(session_factory, project_id="disabled", poll_enabled=False)

        poller = AsyncMock()
        poller.poll = AsyncMock(return_value=[])
        with patch(
            "backend.worker.issue_poller_scheduler.get_poller", return_value=poller
        ) as get_poller:
            sched = IssuePollerScheduler(session_factory, poll_seconds=60)
            await sched._tick()

        # Called exactly once for the enabled project
        assert get_poller.call_count == 1
        poller.poll.assert_awaited_once()

    async def test_tick_advances_next_poll_at(self, session_factory):
        await _insert_project(session_factory, project_id="p1")
        poller = AsyncMock()
        poller.poll = AsyncMock(return_value=[])
        with patch("backend.worker.issue_poller_scheduler.get_poller", return_value=poller):
            sched = IssuePollerScheduler(session_factory, poll_seconds=60)
            await sched._tick()

        async with session_factory() as s:
            p = await s.get(ProjectConfig, "p1")
            assert p is not None
            assert p.next_poll_at is not None
            assert p.last_polled_at is not None
            # Default interval is 5 minutes
            delta = p.next_poll_at - p.last_polled_at
            assert timedelta(minutes=4) < delta < timedelta(minutes=6)

    async def test_tick_isolates_per_project_errors(self, session_factory):
        await _insert_project(session_factory, project_id="ok")
        await _insert_project(session_factory, project_id="bad")

        async def flaky(project, _session):
            if project.project_id == "bad":
                raise RuntimeError("boom")
            return []

        poller = AsyncMock()
        poller.poll.side_effect = flaky
        with patch("backend.worker.issue_poller_scheduler.get_poller", return_value=poller):
            sched = IssuePollerScheduler(session_factory, poll_seconds=60)
            await sched._tick()

        async with session_factory() as s:
            ok = await s.get(ProjectConfig, "ok")
            bad = await s.get(ProjectConfig, "bad")
            assert ok is not None
            assert bad is not None
            # Both still get next_poll_at advanced even when one fails.
            assert ok.next_poll_at is not None
            assert bad.next_poll_at is not None

    async def test_tick_skips_projects_whose_next_poll_is_future(self, session_factory):
        future = datetime.now(UTC) + timedelta(hours=1)
        await _insert_project(session_factory, project_id="later", next_poll_at=future)

        poller = AsyncMock()
        poller.poll = AsyncMock(return_value=[])
        with patch(
            "backend.worker.issue_poller_scheduler.get_poller", return_value=poller
        ) as get_poller:
            sched = IssuePollerScheduler(session_factory, poll_seconds=60)
            await sched._tick()

        get_poller.assert_not_called()
