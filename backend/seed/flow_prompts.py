# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Seed default flow prompts (ADR-009).

Idempotent insert-if-not-exists by name. The ``implement`` and ``pr_review``
flow prompts are the default run definitions resolved by the dispatcher.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import FlowPrompt
from backend.repositories.flow_prompt_repo import FlowPromptRepository

logger = logging.getLogger("agentickode.seed")

DEFAULT_FLOW_PROMPTS = [
    {
        "name": "implement",
        "flow_type": "implement",
        "agent_mode": "task",
        "prompt": (
            "You are an autonomous coding agent. Implement the task described in the "
            "context below: read the repository, make the changes, run the tests, and "
            "open a pull request. Work to completion."
        ),
        "is_system": True,
    },
    {
        "name": "pr-review",
        "flow_type": "pr_review",
        "agent_mode": "generate",
        "prompt": (
            "Review the pull request diff in the context below. Report correctness bugs, "
            "security issues, and notable quality concerns concisely. Do not modify code."
        ),
        "is_system": True,
    },
]


async def seed_flow_prompts(db: AsyncSession) -> None:
    repo = FlowPromptRepository(db)
    created = 0
    for spec in DEFAULT_FLOW_PROMPTS:
        if await repo.get_by_name(spec["name"]) is None:
            await repo.create(FlowPrompt(**spec))
            created += 1
    if created:
        await db.commit()
        logger.info("Seeded %d default flow prompts", created)
