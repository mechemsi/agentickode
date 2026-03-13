# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for F11 cost tracking: estimate_cost helper + analytics aggregation."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from backend.config import DEFAULT_COST_RATE, MODEL_COST_RATES
from backend.models import AgentInvocation, ProjectConfig, TaskRun
from backend.repositories.analytics_repo import AnalyticsRepository
from backend.worker.phases._helpers import estimate_cost, get_token_usage

# === estimate_cost() unit tests ===


class TestEstimateCost:
    def test_claude_agent(self):
        tokens_in, tokens_out, cost = estimate_cost("claude", 4000, 8000)
        assert tokens_in == 1000  # 4000 / 4
        assert tokens_out == 2000  # 8000 / 4
        rate_in, rate_out = MODEL_COST_RATES["claude"]
        expected = (1000 * rate_in + 2000 * rate_out) / 1_000_000
        assert cost == round(expected, 6)

    def test_unknown_agent_uses_default(self):
        tokens_in, tokens_out, cost = estimate_cost("unknown_agent", 400, 800)
        assert tokens_in == 100
        assert tokens_out == 200
        rate_in, rate_out = DEFAULT_COST_RATE
        expected = (100 * rate_in + 200 * rate_out) / 1_000_000
        assert cost == round(expected, 6)

    def test_ollama_subname_uses_zero_cost(self):
        # "ollama/qwen2.5" splits to "ollama" which is in MODEL_COST_RATES at (0.0, 0.0)
        tokens_in, tokens_out, cost = estimate_cost("ollama/qwen2.5", 2000, 4000)
        assert tokens_in == 500
        assert tokens_out == 1000
        assert cost == 0.0

    def test_codex_agent(self):
        tokens_in, tokens_out, cost = estimate_cost("codex", 1200, 2400)
        assert tokens_in == 300
        assert tokens_out == 600
        rate_in, rate_out = MODEL_COST_RATES["codex"]
        expected = (300 * rate_in + 600 * rate_out) / 1_000_000
        assert cost == round(expected, 6)

    def test_zero_chars(self):
        tokens_in, tokens_out, cost = estimate_cost("claude", 0, 0)
        assert tokens_in == 0
        assert tokens_out == 0
        assert cost == 0.0


class TestGetTokenUsage:
    def test_actual_counts_from_adapter(self):
        adapter = MagicMock()
        adapter.last_token_usage = (100, 200)
        tokens_in, tokens_out, cost, source = get_token_usage(adapter, "ollama/qwen2.5", 4000, 8000)
        assert tokens_in == 100
        assert tokens_out == 200
        assert cost == 0.0  # ollama rate is (0.0, 0.0)
        assert source == "api"

    def test_actual_counts_claude_rate(self):
        adapter = MagicMock()
        adapter.last_token_usage = (1000, 2000)
        tokens_in, tokens_out, cost, source = get_token_usage(adapter, "claude", 4000, 8000)
        assert tokens_in == 1000
        assert tokens_out == 2000
        rate_in, rate_out = MODEL_COST_RATES["claude"]
        expected = (1000 * rate_in + 2000 * rate_out) / 1_000_000
        assert cost == round(expected, 6)
        assert source == "api"

    def test_fallback_to_estimated(self):
        adapter = MagicMock(spec=[])  # no last_token_usage attr
        tokens_in, tokens_out, cost, source = get_token_usage(adapter, "claude", 4000, 8000)
        assert tokens_in == 1000  # 4000 // 4
        assert tokens_out == 2000  # 8000 // 4
        assert source == "estimated"

    def test_none_usage_falls_back(self):
        adapter = MagicMock()
        adapter.last_token_usage = None
        tokens_in, tokens_out, cost, source = get_token_usage(adapter, "claude", 4000, 8000)
        assert tokens_in == 1000
        assert source == "estimated"


# === Analytics cost aggregation tests ===


@pytest.fixture()
async def _seed_project(db_session):
    """Seed a project config for FK references."""
    project = ProjectConfig(
        project_id="proj-cost",
        project_slug="cost-test",
        repo_owner="org",
        repo_name="repo",
    )
    db_session.add(project)
    await db_session.flush()


@pytest.fixture()
async def _seed_invocations(db_session, _seed_project):
    """Seed task runs and agent invocations with cost data."""
    now = datetime.utcnow()

    run1 = TaskRun(
        task_id="T-1",
        project_id="proj-cost",
        title="Run 1",
        branch_name="feat/1",
        workspace_path="/w/1",
        status="completed",
        created_at=now,
    )
    run2 = TaskRun(
        task_id="T-2",
        project_id="proj-cost",
        title="Run 2",
        branch_name="feat/2",
        workspace_path="/w/2",
        status="completed",
        created_at=now,
    )
    db_session.add_all([run1, run2])
    await db_session.flush()

    inv1 = AgentInvocation(
        run_id=run1.id,
        agent_name="claude",
        phase_name="planning",
        prompt_chars=4000,
        response_chars=8000,
        estimated_tokens_in=1000,
        estimated_tokens_out=2000,
        estimated_cost_usd=0.033,
        status="success",
        started_at=now,
    )
    inv2 = AgentInvocation(
        run_id=run1.id,
        agent_name="claude",
        phase_name="coding",
        prompt_chars=8000,
        response_chars=16000,
        estimated_tokens_in=2000,
        estimated_tokens_out=4000,
        estimated_cost_usd=0.066,
        status="success",
        started_at=now,
    )
    inv3 = AgentInvocation(
        run_id=run2.id,
        agent_name="codex",
        phase_name="coding",
        prompt_chars=2000,
        response_chars=4000,
        estimated_tokens_in=500,
        estimated_tokens_out=1000,
        estimated_cost_usd=0.009,
        status="success",
        started_at=now,
    )
    db_session.add_all([inv1, inv2, inv3])
    await db_session.commit()


@pytest.mark.asyncio
async def test_cost_stats_aggregation(db_session, _seed_invocations):
    repo = AnalyticsRepository(db_session)
    cutoff = datetime.utcnow() - timedelta(days=1)
    stats = await repo._cost_stats(cutoff)

    assert stats["total_cost_usd"] == round(0.033 + 0.066 + 0.009, 4)
    assert stats["total_tokens_in"] == 1000 + 2000 + 500
    assert stats["total_tokens_out"] == 2000 + 4000 + 1000
    # 2 runs: run1 cost=0.099, run2 cost=0.009 → avg=0.054
    assert stats["avg_cost_per_run_usd"] == round((0.099 + 0.009) / 2, 4)

    by_agent = {c["agent_name"]: c["cost_usd"] for c in stats["cost_by_agent"]}
    assert by_agent["claude"] == round(0.033 + 0.066, 4)
    assert by_agent["codex"] == round(0.009, 4)


@pytest.mark.asyncio
async def test_cost_stats_empty(db_session, _seed_project):
    repo = AnalyticsRepository(db_session)
    cutoff = datetime.utcnow() - timedelta(days=1)
    stats = await repo._cost_stats(cutoff)

    assert stats["total_cost_usd"] == 0.0
    assert stats["total_tokens_in"] == 0
    assert stats["total_tokens_out"] == 0
    assert stats["avg_cost_per_run_usd"] == 0.0
    assert stats["cost_by_agent"] == []


@pytest.mark.asyncio
async def test_analytics_summary_includes_cost(db_session, _seed_invocations):
    repo = AnalyticsRepository(db_session)
    summary = await repo.get_summary(days=14)

    assert "cost_stats" in summary
    assert summary["cost_stats"]["total_cost_usd"] > 0
    assert len(summary["cost_stats"]["cost_by_agent"]) > 0
