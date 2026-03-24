# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.policy_enforcer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from backend.services.policy_enforcer import PolicyEnforcer


def _make_policy(
    max_episodes: int = 3,
    max_turns_per_episode: int = 30,
    max_total_duration_seconds: int = 7200,
    stall_timeout_seconds: int = 600,
    max_budget_usd: float | None = 10.0,
):
    policy = MagicMock()
    policy.max_episodes = max_episodes
    policy.max_turns_per_episode = max_turns_per_episode
    policy.max_total_duration_seconds = max_total_duration_seconds
    policy.stall_timeout_seconds = stall_timeout_seconds
    policy.max_budget_usd = max_budget_usd
    return policy


def _make_loop_exec(
    total_episodes: int = 0,
    started_at: datetime | None = None,
    total_tokens: int = 0,
):
    loop_exec = MagicMock()
    loop_exec.total_episodes = total_episodes
    loop_exec.started_at = started_at or datetime.now(UTC)
    loop_exec.total_tokens = total_tokens
    return loop_exec


def _make_episode(episode_number: int = 1, turn_count: int = 0):
    ep = MagicMock()
    ep.episode_number = episode_number
    ep.turn_count = turn_count
    return ep


class TestNoPolicyDefaults:
    """When no policy is set, enforcer returns no violations and defaults."""

    def test_no_policy_returns_no_violations_before_episode(self):
        enforcer = PolicyEnforcer(None)
        loop_exec = _make_loop_exec(total_episodes=100)
        assert enforcer.check_before_episode(loop_exec) == []

    def test_no_policy_returns_no_violations_during_episode(self):
        enforcer = PolicyEnforcer(None)
        episode = _make_episode(turn_count=9999)
        assert enforcer.check_during_episode(episode) == []

    def test_no_policy_default_values(self):
        enforcer = PolicyEnforcer(None)
        assert enforcer.has_policy is False
        assert enforcer.max_turns == 30
        assert enforcer.max_episodes == 5
        assert enforcer.stall_timeout == 600


class TestMaxEpisodes:
    """Violation when episode count reaches or exceeds max."""

    def test_max_episodes_reached_returns_violation(self):
        policy = _make_policy(max_episodes=3)
        enforcer = PolicyEnforcer(policy)
        loop_exec = _make_loop_exec(total_episodes=3)

        violations = enforcer.check_before_episode(loop_exec)

        assert len(violations) == 1
        assert "Max episodes (3) reached" in violations[0]

    def test_under_max_episodes_no_violation(self):
        policy = _make_policy(max_episodes=3)
        enforcer = PolicyEnforcer(policy)
        loop_exec = _make_loop_exec(total_episodes=2)

        violations = enforcer.check_before_episode(loop_exec)

        episode_violations = [v for v in violations if "episodes" in v.lower()]
        assert episode_violations == []


class TestDurationExceeded:
    """Violation when total duration exceeds max."""

    def test_duration_exceeded_returns_violation(self):
        policy = _make_policy(max_total_duration_seconds=7200)
        enforcer = PolicyEnforcer(policy)
        loop_exec = _make_loop_exec(
            started_at=datetime.now(UTC) - timedelta(hours=3),
        )

        violations = enforcer.check_before_episode(loop_exec)

        duration_violations = [v for v in violations if "duration" in v.lower()]
        assert len(duration_violations) == 1
        assert "7200s" in duration_violations[0]

    def test_within_duration_no_violation(self):
        policy = _make_policy(max_total_duration_seconds=7200)
        enforcer = PolicyEnforcer(policy)
        loop_exec = _make_loop_exec(
            started_at=datetime.now(UTC) - timedelta(hours=1),
        )

        violations = enforcer.check_before_episode(loop_exec)

        duration_violations = [v for v in violations if "duration" in v.lower()]
        assert duration_violations == []


class TestBudgetExceeded:
    """Violation when estimated cost exceeds budget."""

    def test_budget_exceeded_returns_violation(self):
        policy = _make_policy(max_budget_usd=10.0)
        enforcer = PolicyEnforcer(policy)
        # 700_000 tokens * 0.000015 = $10.50 -> exceeds $10
        loop_exec = _make_loop_exec(total_tokens=700_000)

        violations = enforcer.check_before_episode(loop_exec)

        budget_violations = [v for v in violations if "budget" in v.lower()]
        assert len(budget_violations) == 1
        assert "$10.00" in budget_violations[0]

    def test_within_budget_no_violation(self):
        policy = _make_policy(max_budget_usd=10.0)
        enforcer = PolicyEnforcer(policy)
        # 1000 tokens * 0.000015 = $0.015 -> well within budget
        loop_exec = _make_loop_exec(total_tokens=1000)

        violations = enforcer.check_before_episode(loop_exec)

        budget_violations = [v for v in violations if "budget" in v.lower()]
        assert budget_violations == []


class TestTurnLimit:
    """Violation when turn count exceeds per-episode max during episode."""

    def test_turn_limit_exceeded_returns_violation(self):
        policy = _make_policy(max_turns_per_episode=30)
        enforcer = PolicyEnforcer(policy)
        episode = _make_episode(episode_number=2, turn_count=31)

        violations = enforcer.check_during_episode(episode)

        assert len(violations) == 1
        assert "Turn limit (30) exceeded" in violations[0]
        assert "episode 2" in violations[0]

    def test_within_turn_limit_no_violation(self):
        policy = _make_policy(max_turns_per_episode=30)
        enforcer = PolicyEnforcer(policy)
        episode = _make_episode(turn_count=15)

        violations = enforcer.check_during_episode(episode)

        assert violations == []


class TestProperties:
    """Properties return policy values when set."""

    def test_properties_with_policy(self):
        policy = _make_policy(
            max_episodes=10,
            max_turns_per_episode=50,
            stall_timeout_seconds=900,
        )
        enforcer = PolicyEnforcer(policy)

        assert enforcer.has_policy is True
        assert enforcer.max_turns == 50
        assert enforcer.max_episodes == 10
        assert enforcer.stall_timeout == 900
