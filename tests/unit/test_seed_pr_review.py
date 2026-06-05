# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for the restored pr-review system workflow template."""

from sqlalchemy import select

from backend.models import WorkflowTemplate
from backend.seed.workflow_templates import (
    _DEPRECATED_SYSTEM_TEMPLATES,
    seed_workflow_templates,
)


def _pr_review_def() -> dict:
    from backend.seed.workflow_templates import DEFAULT_WORKFLOW_TEMPLATES

    return next(t for t in DEFAULT_WORKFLOW_TEMPLATES if t["name"] == "pr-review")


class TestPrReviewTemplate:
    async def test_pr_review_not_deprecated(self):
        assert "pr-review" not in _DEPRECATED_SYSTEM_TEMPLATES

    async def test_seed_creates_pr_review_template(self, db_session):
        await seed_workflow_templates(db_session)

        result = await db_session.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.name == "pr-review")
        )
        tpl = result.scalar_one()
        assert tpl.is_system is True
        assert tpl.is_default is False

        phase_names = [p["phase_name"] for p in tpl.phases]
        assert phase_names == ["pr_fetch", "reviewing", "finalization"]

        reviewing = next(p for p in tpl.phases if p["phase_name"] == "reviewing")
        assert reviewing["uses_agent"] is True
        assert reviewing["agent_mode"] == "generate"

    async def test_pr_review_triggers_are_label_gated_pr_events(self, db_session):
        await seed_workflow_templates(db_session)

        result = await db_session.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.name == "pr-review")
        )
        tpl = result.scalar_one()

        sources = {t["source"] for t in tpl.triggers}
        assert {"github", "gitea"} <= sources
        for trigger in tpl.triggers:
            assert trigger["type"] == "pr_event"
            assert trigger["label_filter"] == ["ai-review"]

    async def test_seed_reconciles_stale_system_triggers(self, db_session):
        """A pre-existing system pr-review row with stale label-triggers gets re-synced.

        Regression for the upgrade path where a v0.5.0/0.5.1 DB carried
        ``triggers=[{type:'label'}]`` (label_rules backfilled by migration 037) and
        was never pruned — TriggerMatcher would never match the pr_event, silently
        killing the feature.
        """
        db_session.add(
            WorkflowTemplate(
                name="pr-review",
                description="stale",
                is_system=True,
                is_default=False,
                label_rules=[],
                triggers=[{"type": "label", "source": "github", "match_any": ["review-pr"]}],
                phases=[{"phase_name": "reviewing", "enabled": True}],
            )
        )
        await db_session.commit()

        await seed_workflow_templates(db_session)

        result = await db_session.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.name == "pr-review")
        )
        tpl = result.scalar_one()  # still exactly one row
        trigger_types = {t["type"] for t in tpl.triggers}
        assert trigger_types == {"pr_event"}
        assert [p["phase_name"] for p in tpl.phases] == ["pr_fetch", "reviewing", "finalization"]

    async def test_operator_custom_pr_review_not_clobbered(self, db_session):
        """A non-system (operator) pr-review template must be left untouched by seed."""
        db_session.add(
            WorkflowTemplate(
                name="pr-review",
                description="mine",
                is_system=False,
                is_default=False,
                label_rules=[],
                triggers=[{"type": "label", "match_any": ["custom"]}],
                phases=[{"phase_name": "reviewing", "enabled": True}],
            )
        )
        await db_session.commit()

        await seed_workflow_templates(db_session)

        result = await db_session.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.name == "pr-review")
        )
        tpl = result.scalar_one()
        assert tpl.is_system is False
        assert tpl.description == "mine"
        assert {t["type"] for t in tpl.triggers} == {"label"}

    async def test_double_seed_keeps_pr_review(self, db_session):
        """pr-review must survive a second seed (not pruned as deprecated)."""
        await seed_workflow_templates(db_session)
        await seed_workflow_templates(db_session)

        result = await db_session.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.name == "pr-review")
        )
        assert len(result.scalars().all()) == 1
