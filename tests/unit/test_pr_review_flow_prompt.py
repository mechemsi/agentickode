# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for PR-review → flow-prompt binding (ADR-009 Phase 2)."""

from backend.api._pr_webhook_helpers import resolve_pr_review_flow_prompt_id
from backend.config import settings
from backend.models import FlowPrompt
from backend.repositories.flow_prompt_repo import FlowPromptRepository


class TestResolvePrReviewFlowPromptId:
    async def test_none_when_flag_off(self, db_session, monkeypatch):
        monkeypatch.setattr(settings, "flow_prompts_enabled", False)
        await FlowPromptRepository(db_session).create(
            FlowPrompt(name="pr-review", flow_type="pr_review", prompt="x", agent_mode="generate")
        )
        await db_session.commit()
        assert await resolve_pr_review_flow_prompt_id(db_session) is None

    async def test_none_when_flag_on_but_no_flow(self, db_session, monkeypatch):
        monkeypatch.setattr(settings, "flow_prompts_enabled", True)
        assert await resolve_pr_review_flow_prompt_id(db_session) is None

    async def test_returns_id_when_flag_on_and_flow_exists(self, db_session, monkeypatch):
        monkeypatch.setattr(settings, "flow_prompts_enabled", True)
        repo = FlowPromptRepository(db_session)
        flow = await repo.create(
            FlowPrompt(name="pr-review", flow_type="pr_review", prompt="x", agent_mode="generate")
        )
        await db_session.commit()
        assert await resolve_pr_review_flow_prompt_id(db_session) == flow.id
