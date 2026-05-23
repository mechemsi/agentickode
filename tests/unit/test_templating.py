# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.worker.steps.templating.render."""

from unittest.mock import MagicMock

from backend.worker.steps.templating import render


class TestRender:
    async def test_returns_unchanged_when_no_placeholders(self, db_session):
        task_run = MagicMock(id=1)
        result = await render("echo hello", task_run, db_session)
        assert result == "echo hello"

    async def test_substitutes_run_field(self, db_session, make_task_run):
        run = make_task_run(title="My Title")
        result = await render("Title: {{run.title}}", run, db_session)
        assert result == "Title: My Title"

    async def test_substitutes_missing_run_field_to_empty(self, db_session, make_task_run):
        run = make_task_run()
        result = await render("X={{run.nonexistent}}Y", run, db_session)
        assert result == "X=Y"

    async def test_substitutes_step_output(self, db_session, make_task_run):
        from backend.models import PhaseExecution, ProjectConfig

        project = ProjectConfig(
            project_id="proj-tpl",
            project_slug="tpl",
            repo_owner="o",
            repo_name="r",
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-tpl")
        db_session.add(run)
        await db_session.commit()

        pe = PhaseExecution(
            run_id=run.id,
            phase_name="build",
            order_index=0,
            status="completed",
            result={"sha": "abc123"},
        )
        db_session.add(pe)
        await db_session.commit()

        result = await render("Built {{steps.build.sha}}", run, db_session)
        assert result == "Built abc123"

    async def test_substitutes_missing_step_to_empty(self, db_session, make_task_run):
        from backend.models import ProjectConfig

        project = ProjectConfig(
            project_id="proj-tpl2",
            project_slug="tpl2",
            repo_owner="o",
            repo_name="r",
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-tpl2")
        db_session.add(run)
        await db_session.commit()

        result = await render("X={{steps.nonexistent.field}}Y", run, db_session)
        assert result == "X=Y"
