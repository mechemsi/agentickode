# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for repository classes."""

from backend.models import ProjectConfig
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.task_run_repo import TaskRunRepository


class TestTaskRunRepository:
    async def test_list_runs_empty(self, db_session):
        repo = TaskRunRepository(db_session)
        runs, total = await repo.list_runs()
        assert runs == []
        assert total == 0

    async def test_add_and_get(self, db_session, make_task_run):
        # Need a project first (FK constraint)
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        repo = TaskRunRepository(db_session)
        run = make_task_run()
        repo.add(run)
        await repo.commit()

        found = await repo.get_by_id(run.id)
        assert found is not None
        assert found.title == "Test task"

    async def test_get_stats(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        repo = TaskRunRepository(db_session)
        for status in ["pending", "pending", "running", "completed"]:
            run = make_task_run(task_id=f"T-{status}-{id(status)}", status=status)
            repo.add(run)
        await repo.commit()

        stats = await repo.get_stats()
        assert stats["total_runs"] == 4
        assert stats["pending"] == 2
        assert stats["running"] == 1

    async def test_get_pending(self, db_session, make_task_run):
        project = ProjectConfig(
            project_id="proj-1",
            project_slug="test",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        db_session.add(project)
        await db_session.commit()

        repo = TaskRunRepository(db_session)
        run = make_task_run(status="pending")
        repo.add(run)
        await repo.commit()

        pending = await repo.get_pending(limit=5)
        assert len(pending) == 1


class TestProjectConfigRepository:
    async def test_list_all_empty(self, db_session):
        repo = ProjectConfigRepository(db_session)
        projects = await repo.list_all()
        assert projects == []

    async def test_create_and_get(self, db_session):
        repo = ProjectConfigRepository(db_session)
        project = ProjectConfig(
            project_id="p1",
            project_slug="slug",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        created = await repo.create(project)
        assert created.project_id == "p1"

        found = await repo.get_by_id("p1")
        assert found is not None
        assert found.project_slug == "slug"

    async def test_get_by_git_repo(self, db_session):
        repo = ProjectConfigRepository(db_session)
        project = ProjectConfig(
            project_id="p1",
            project_slug="slug",
            repo_owner="myorg",
            repo_name="myrepo",
            default_branch="main",
            git_provider="github",
        )
        await repo.create(project)

        found = await repo.get_by_git_repo("github", "myorg", "myrepo")
        assert found is not None
        assert found.project_id == "p1"

    async def test_update(self, db_session):
        repo = ProjectConfigRepository(db_session)
        project = ProjectConfig(
            project_id="p1",
            project_slug="old",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        await repo.create(project)

        updated = await repo.update(project, {"project_slug": "new"})
        assert updated.project_slug == "new"

    async def test_delete(self, db_session):
        repo = ProjectConfigRepository(db_session)
        project = ProjectConfig(
            project_id="p1",
            project_slug="slug",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
        )
        await repo.create(project)

        await repo.delete(project)
        assert await repo.get_by_id("p1") is None