# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Centralized seed data for fresh installations.

All default/fixture data lives here. Called from lifespan startup.
Uses insert-if-not-exists to preserve user customizations.

Modules:
    agent_settings     - CLI agent definitions (AgentSettings table)
    workflow_templates - Pipeline phase sequences
    role_configs       - System prompts per role
    prompt_overrides   - Per-CLI-agent prompt customizations
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.seed.agent_settings import DEFAULT_AGENT_SETTINGS, seed_agent_settings
from backend.seed.prompt_overrides import AGENT_PROMPT_OVERRIDES, seed_prompt_overrides
from backend.seed.role_configs import DEFAULT_ROLE_CONFIGS, seed_role_configs
from backend.seed.workflow_templates import DEFAULT_WORKFLOW_TEMPLATES, seed_workflow_templates

logger = logging.getLogger("agentickode.seed")

# Re-export everything that external code imports from `backend.seed`.
# Keep private helpers accessible for tests that import them directly.
_seed_agent_settings = seed_agent_settings

__all__ = [
    "AGENT_PROMPT_OVERRIDES",
    "DEFAULT_AGENT_SETTINGS",
    "DEFAULT_ROLE_CONFIGS",
    "DEFAULT_WORKFLOW_TEMPLATES",
    "_seed_agent_settings",
    "seed_all",
]


async def seed_all(db: AsyncSession) -> None:
    """Run all seed operations. Safe to call repeatedly (idempotent)."""
    await seed_agent_settings(db)
    await seed_workflow_templates(db)
    await seed_role_configs(db)
    await seed_prompt_overrides(db)
    logger.info("Seed data applied successfully")
