# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for flow prompts (ADR-009, Phase 1)."""

from types import SimpleNamespace

from backend.models import FlowPrompt
from backend.repositories.flow_prompt_repo import FlowPromptRepository
from backend.worker.flow.data_sources import (
    FLOW_TYPE_SOURCES,
    fetch_flow_data,
    sources_for,
)
from backend.worker.flow.executor import _compose_prompt


class TestFlowPromptRepo:
    async def test_create_and_get_by_name(self, db_session):
        repo = FlowPromptRepository(db_session)
        await repo.create(FlowPrompt(name="impl", flow_type="implement", prompt="do it"))
        await db_session.commit()
        got = await repo.get_by_name("impl")
        assert got is not None and got.flow_type == "implement"

    async def test_get_by_flow_type_only_enabled(self, db_session):
        repo = FlowPromptRepository(db_session)
        await repo.create(
            FlowPrompt(name="r-off", flow_type="pr_review", prompt="x", enabled=False)
        )
        await repo.create(FlowPrompt(name="r-on", flow_type="pr_review", prompt="y", enabled=True))
        await db_session.commit()
        got = await repo.get_by_flow_type("pr_review")
        assert got is not None and got.name == "r-on"

    async def test_get_by_flow_type_missing(self, db_session):
        repo = FlowPromptRepository(db_session)
        assert await repo.get_by_flow_type("nope") is None


class TestSeed:
    async def test_seed_creates_implement_and_pr_review(self, db_session):
        from backend.seed.flow_prompts import seed_flow_prompts

        await seed_flow_prompts(db_session)
        repo = FlowPromptRepository(db_session)
        # Phase 3 default resolves the implement flow prompt by type:
        impl = await repo.get_by_flow_type("implement")
        assert impl is not None and impl.agent_mode == "task"
        pr = await repo.get_by_flow_type("pr_review")
        assert pr is not None and pr.agent_mode == "generate"

    async def test_seed_is_idempotent(self, db_session):
        from backend.seed.flow_prompts import seed_flow_prompts

        await seed_flow_prompts(db_session)
        await seed_flow_prompts(db_session)
        rows = await FlowPromptRepository(db_session).list_all()
        names = [r.name for r in rows]
        assert names.count("implement") == 1
        assert names.count("pr-review") == 1


class TestSourcesFor:
    def test_fixed_sources_per_type(self):
        flow = SimpleNamespace(flow_type="implement", extra_data_sources=None)
        assert sources_for(flow) == FLOW_TYPE_SOURCES["implement"]

    def test_extra_appended_and_deduped(self):
        flow = SimpleNamespace(
            flow_type="pr_review", extra_data_sources=["pr_diff", "repo_context"]
        )
        # pr_diff is already fixed for pr_review → not duplicated; repo_context appended
        assert sources_for(flow) == ["pr_diff", "repo_context"]

    def test_unknown_flow_type_uses_only_extras(self):
        flow = SimpleNamespace(flow_type="custom", extra_data_sources=["repo_context"])
        assert sources_for(flow) == ["repo_context"]


class TestFetchFlowData:
    async def test_gathers_known_skips_unknown(
        self, db_session, mock_services, make_task_run, seed_proj1
    ):
        run = make_task_run(title="T", description="D", repo_owner="o", repo_name="r")
        db_session.add(run)
        await db_session.commit()
        flow = SimpleNamespace(flow_type="implement", extra_data_sources=["bogus_source"])
        data = await fetch_flow_data(run, db_session, mock_services, flow)
        assert "repo_context" in data
        assert data["repo_context"]["repo"] == "o/r"
        assert "issue_body" in data
        assert "bogus_source" not in data  # unknown skipped, not fatal


class TestComposePrompt:
    def test_no_data_returns_prompt(self):
        assert _compose_prompt("hello", {}) == "hello"

    def test_appends_context_block(self):
        out = _compose_prompt("hello", {"repo_context": {"repo": "o/r"}})
        assert out.startswith("hello")
        assert "Context (fetched by AgenticKode)" in out
        assert "o/r" in out
