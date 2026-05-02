# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for GitHubIssuePoller."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.models import ProjectConfig, TaskRun
from backend.services.task_source_polling.github_poller import GitHubIssuePoller


@pytest.fixture()
async def gh_project(db_session):
    p = ProjectConfig(
        project_id="gh-proj",
        project_slug="gh-proj",
        repo_owner="acme",
        repo_name="widgets",
        default_branch="main",
        task_source="github",
        git_provider="github",
        workspace_path="/workspaces/widgets",
        poll_enabled=True,
        poll_interval_minutes=5,
        integration_config={},
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


class _FakeProvider:
    def __init__(self, issues):
        self._issues = issues

    async def list_issues(self, *_, **__):
        return self._issues


def _patch_provider(issues):
    return patch(
        "backend.services.task_source_polling.github_poller.get_git_provider",
        return_value=_FakeProvider(issues),
    )


class TestGitHubIssuePoller:
    async def test_creates_runs_only_for_ai_task_issues(self, db_session, gh_project):
        issues = [
            {"number": 1, "title": "keep", "body": "a", "labels": ["ai-task"], "url": ""},
            {"number": 2, "title": "skip", "body": "b", "labels": ["docs"], "url": ""},
            {
                "number": 3,
                "title": "claude",
                "body": "c",
                "labels": ["ai-task", "use-claude"],
                "url": "",
            },
        ]
        with _patch_provider(issues):
            created = await GitHubIssuePoller().poll(gh_project, db_session)
        await db_session.commit()

        from sqlalchemy import select

        runs = (await db_session.execute(select(TaskRun).order_by(TaskRun.task_id))).scalars().all()
        assert len(created) == 2
        assert len(runs) == 2
        assert {r.task_id for r in runs} == {"1", "3"}
        claude_run = next(r for r in runs if r.task_id == "3")
        assert claude_run.use_claude_api is True
        first_run = next(r for r in runs if r.task_id == "1")
        assert first_run.task_source_meta["repo_full_name"] == "acme/widgets"
        assert first_run.task_source == "github"

    async def test_dedupes_against_existing_task_runs(self, db_session, gh_project):
        existing = TaskRun(
            task_id="7",
            project_id=gh_project.project_id,
            title="old",
            description="",
            branch_name="feature/ai-7",
            workspace_path="/workspaces/x",
            repo_owner="acme",
            repo_name="widgets",
            default_branch="main",
            task_source="github",
            git_provider="github",
            task_source_meta={},
        )
        db_session.add(existing)
        await db_session.commit()

        issues = [
            {"number": 7, "title": "dupe", "body": "", "labels": ["ai-task"], "url": ""},
            {"number": 8, "title": "new", "body": "", "labels": ["ai-task"], "url": ""},
        ]
        with _patch_provider(issues):
            created = await GitHubIssuePoller().poll(gh_project, db_session)
        await db_session.commit()

        assert len(created) == 1
        from sqlalchemy import select

        runs = (await db_session.execute(select(TaskRun))).scalars().all()
        assert {r.task_id for r in runs} == {"7", "8"}

    async def test_swallows_provider_errors(self, db_session, gh_project):
        broken = AsyncMock(side_effect=RuntimeError("boom"))
        with patch(
            "backend.services.task_source_polling.github_poller.get_git_provider",
            return_value=type("P", (), {"list_issues": broken})(),
        ):
            created = await GitHubIssuePoller().poll(gh_project, db_session)
        assert created == []
