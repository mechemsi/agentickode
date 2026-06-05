# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""PR-review runs must use their bound template, not the project execution_mode."""

import pytest
from sqlalchemy import select

from backend.models import ProjectConfig, WorkflowTemplate
from backend.seed.workflow_templates import seed_workflow_templates
from backend.worker.pipeline import _resolve_workflow_phases


async def _seed_pr_review_template(db_session) -> WorkflowTemplate:
    await seed_workflow_templates(db_session)
    result = await db_session.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.name == "pr-review")
    )
    return result.scalar_one()


class TestPrReviewPhaseResolution:
    async def test_autonomous_project_still_runs_pr_review_template(
        self, db_session, make_task_run
    ):
        """An autonomous-mode project must not divert a PR-review run to agent_loop."""
        db_session.add(
            ProjectConfig(
                project_id="auto-proj",
                project_slug="auto",
                repo_owner="o",
                repo_name="r",
                autonomy_config={"execution_mode": "autonomous"},
            )
        )
        await db_session.commit()
        tpl = await _seed_pr_review_template(db_session)

        run = make_task_run(
            project_id="auto-proj",
            workflow_template_id=tpl.id,
            task_source_meta={"review_mode": "comment", "pr_number": 3},
        )
        db_session.add(run)
        await db_session.commit()

        phases = await _resolve_workflow_phases(run, db_session)
        assert [p["phase_name"] for p in phases] == ["pr_fetch", "reviewing", "finalization"]

    async def test_pr_review_run_with_lost_binding_recovers_by_name(
        self, db_session, make_task_run
    ):
        """If the FK binding was NULLed, re-resolve the pr-review template by name."""
        db_session.add(
            ProjectConfig(
                project_id="p2",
                project_slug="p2",
                repo_owner="o",
                repo_name="r",
                autonomy_config={"execution_mode": "autonomous"},
            )
        )
        await db_session.commit()
        await _seed_pr_review_template(db_session)

        run = make_task_run(
            project_id="p2",
            workflow_template_id=None,  # binding lost (e.g. seed pruned the old row)
            task_source_meta={"review_mode": "comment", "pr_number": 4},
        )
        db_session.add(run)
        await db_session.commit()

        phases = await _resolve_workflow_phases(run, db_session)
        assert [p["phase_name"] for p in phases] == ["pr_fetch", "reviewing", "finalization"]

    async def test_pr_review_run_with_no_template_raises(self, db_session, make_task_run):
        """A review run with no resolvable pr-review template must fail loudly, not run the coder."""
        db_session.add(
            ProjectConfig(
                project_id="p3",
                project_slug="p3",
                repo_owner="o",
                repo_name="r",
                autonomy_config={"execution_mode": "autonomous"},
            )
        )
        await db_session.commit()  # no pr-review template seeded

        run = make_task_run(
            project_id="p3",
            workflow_template_id=None,
            task_source_meta={"review_mode": "comment", "pr_number": 5},
        )
        db_session.add(run)
        await db_session.commit()

        with pytest.raises(RuntimeError, match="PR-review run"):
            await _resolve_workflow_phases(run, db_session)
