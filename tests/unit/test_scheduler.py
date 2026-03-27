# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.agents import ScheduledTask
from backend.worker.scheduler import TaskScheduler


def _make_scheduled_task(
    task_id: int = 1,
    project_id: str = "test/project",
    name: str = "Nightly checks",
    schedule: str = "0 3 * * *",
    task_description: str = "Run security scan",
    enabled: bool = True,
) -> MagicMock:
    task = MagicMock(spec=ScheduledTask)
    task.id = task_id
    task.project_id = project_id
    task.name = name
    task.schedule = schedule
    task.task_description = task_description
    task.enabled = enabled
    task.last_run_at = None
    task.next_run_at = datetime(2026, 3, 28, 3, 0, tzinfo=UTC)
    return task


class TestTaskSchedulerDispatch:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_project(self):
        project = MagicMock()
        project.project_id = "test/project"
        project.repo_owner = "test"
        project.repo_name = "project"
        project.default_branch = "main"
        project.git_provider = "github"
        project.workspace_path = "/workspaces/test-project"
        project.workspace_config = {}
        project.autonomy_config = {"execution_mode": "autonomous"}
        return project

    @pytest.mark.asyncio
    async def test_dispatch_creates_task_run(self, mock_session, mock_project):
        task = _make_scheduled_task()
        mock_repo = AsyncMock()
        mock_repo.mark_executed = AsyncMock()

        with patch("backend.worker.scheduler.ProjectConfigRepository") as mock_project_repo_cls:
            mock_project_repo_cls.return_value.get_by_id = AsyncMock(return_value=mock_project)

            scheduler = TaskScheduler.__new__(TaskScheduler)
            await scheduler._dispatch(task, mock_session, mock_repo)

        mock_session.add.assert_called_once()
        added_run = mock_session.add.call_args[0][0]
        assert added_run.task_source == "scheduled"
        assert added_run.project_id == "test/project"
        assert "[Scheduled]" in added_run.title
        assert added_run.execution_mode == "autonomous"
        mock_repo.mark_executed.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_skips_missing_project(self, mock_session):
        task = _make_scheduled_task()
        mock_repo = AsyncMock()

        with patch("backend.worker.scheduler.ProjectConfigRepository") as mock_project_repo_cls:
            mock_project_repo_cls.return_value.get_by_id = AsyncMock(return_value=None)

            scheduler = TaskScheduler.__new__(TaskScheduler)
            await scheduler._dispatch(task, mock_session, mock_repo)

        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_sets_correct_task_source_meta(self, mock_session, mock_project):
        task = _make_scheduled_task(task_id=42, name="Weekly scan")
        mock_repo = AsyncMock()
        mock_repo.mark_executed = AsyncMock()

        with patch("backend.worker.scheduler.ProjectConfigRepository") as mock_project_repo_cls:
            mock_project_repo_cls.return_value.get_by_id = AsyncMock(return_value=mock_project)

            scheduler = TaskScheduler.__new__(TaskScheduler)
            await scheduler._dispatch(task, mock_session, mock_repo)

        added_run = mock_session.add.call_args[0][0]
        meta = added_run.task_source_meta
        assert meta["scheduled_task_id"] == 42
        assert meta["scheduled_task_name"] == "Weekly scan"
        assert meta["schedule"] == "0 3 * * *"
