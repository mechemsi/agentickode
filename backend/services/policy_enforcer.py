# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Policy enforcer — checks agent budget and safety limits.

Called by the EpisodeRunner before and during each episode to ensure
the agent stays within configured policy bounds.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from backend.models.agents import AgentLoopExecution
from backend.models.episodes import Episode
from backend.models.policies import AgentPolicy

logger = logging.getLogger("agentickode.policy_enforcer")


class PolicyEnforcer:
    """Enforce agent policies during episodic execution."""

    def __init__(self, policy: AgentPolicy | None):
        self._policy = policy

    def check_before_episode(self, loop_exec: AgentLoopExecution) -> list[str]:
        """Check policy limits before starting a new episode.

        Returns a list of violation descriptions. Empty list = OK.
        """
        if not self._policy:
            return []

        violations: list[str] = []

        # Check episode count
        if loop_exec.total_episodes >= self._policy.max_episodes:
            violations.append(f"Max episodes ({self._policy.max_episodes}) reached")

        # Check total duration
        if loop_exec.started_at:
            elapsed = (datetime.now(UTC) - loop_exec.started_at).total_seconds()
            if elapsed >= self._policy.max_total_duration_seconds:
                violations.append(
                    f"Max duration ({self._policy.max_total_duration_seconds}s) exceeded"
                )

        # Check budget (estimated from token usage)
        if self._policy.max_budget_usd is not None:
            estimated_cost = _estimate_cost(loop_exec.total_tokens)
            if estimated_cost >= self._policy.max_budget_usd:
                violations.append(
                    f"Budget limit (${self._policy.max_budget_usd:.2f}) exceeded "
                    f"(estimated ${estimated_cost:.4f})"
                )

        return violations

    def check_during_episode(self, episode: Episode) -> list[str]:
        """Check policy limits during a running episode.

        Returns a list of violation descriptions. Empty list = OK.
        """
        if not self._policy:
            return []

        violations: list[str] = []

        # Check turn count
        if episode.turn_count > self._policy.max_turns_per_episode:
            violations.append(
                f"Turn limit ({self._policy.max_turns_per_episode}) exceeded "
                f"in episode {episode.episode_number}"
            )

        return violations

    @property
    def has_policy(self) -> bool:
        return self._policy is not None

    @property
    def max_turns(self) -> int:
        if self._policy:
            return int(self._policy.max_turns_per_episode)
        return 30

    @property
    def max_episodes(self) -> int:
        if self._policy:
            return int(self._policy.max_episodes)
        return 5

    @property
    def stall_timeout(self) -> int:
        if self._policy:
            return int(self._policy.stall_timeout_seconds)
        return 600


def _estimate_cost(total_tokens: int) -> float:
    """Rough cost estimate from token count.

    Uses approximate Claude pricing. Real cost tracking should use
    actual API-reported token counts stored in AgentInvocation.
    """
    # Approximate blended rate: $0.015 per 1K tokens
    return total_tokens * 0.000015
