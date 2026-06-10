# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Centralized seed data for fresh installations.

All default/fixture data lives here. Called from lifespan startup.
Uses insert-if-not-exists to preserve user customizations.

Modules:
    agent_settings     - CLI agent definitions (AgentSettings table)
    flow_prompts       - Flow-prompt run definitions (ADR-009)
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.seed.agent_settings import DEFAULT_AGENT_SETTINGS, seed_agent_settings
from backend.seed.flow_prompts import seed_flow_prompts
from backend.seed.platform_server import seed_platform_server

logger = logging.getLogger("agentickode.seed")

# Re-export everything that external code imports from `backend.seed`.
# Keep private helpers accessible for tests that import them directly.
_seed_agent_settings = seed_agent_settings

__all__ = [
    "DEFAULT_AGENT_SETTINGS",
    "_seed_agent_settings",
    "seed_all",
]


async def seed_all(db: AsyncSession) -> None:
    """Run all seed operations. Safe to call repeatedly (idempotent)."""
    await seed_agent_settings(db)
    await seed_flow_prompts(db)
    await seed_platform_server(db)
    logger.info("Seed data applied successfully")
