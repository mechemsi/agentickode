# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Seed data for role configs (system prompts per role)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import RoleConfig

logger = logging.getLogger("autodev.seed")

DEFAULT_ROLE_CONFIGS: list[dict] = [
    {
        "agent_name": "planner",
        "display_name": "Planner",
        "description": "Task decomposition and planning agent",
        "is_system": True,
        "system_prompt": (
            "You are a senior software architect specializing in task decomposition.\n\n"
            "You analyze tasks and break them down into specific, implementable subtasks "
            "ordered by dependency."
        ),
        "user_prompt_template": (
            "## Task\nTitle: {title}\nDescription: {description}\n\n"
            "## Project Context\n{context_text}\n\n"
            "## Instructions\n"
            "1. Analyze the task requirements\n"
            "2. Break down into specific, implementable subtasks\n"
            "3. Order subtasks by dependency (what must be done first)\n"
            "4. Estimate complexity (simple/medium/complex)\n\n"
            "Respond in JSON format:\n"
            '{{\n  "subtasks": [\n'
            '    {{"id": 1, "title": "...", "description": "...", '
            '"files_likely_affected": ["..."]}}\n'
            "  ],\n"
            '  "estimated_complexity": "simple|medium|complex",\n'
            '  "notes": "Any important considerations"\n}}'
        ),
    },
    {
        "agent_name": "coder",
        "display_name": "Coder",
        "description": "Code implementation agent",
        "is_system": True,
        "system_prompt": (
            "You are an expert software developer implementing code changes.\n\n"
            "IMPORTANT: You are running autonomously. Do NOT ask clarifying questions. "
            "Make your best judgment and implement the changes directly.\n\n"
            "Follow existing code patterns and style. Add appropriate error handling. "
            "Write or update tests if applicable. Commit changes with descriptive messages."
        ),
        "user_prompt_template": (
            "## Subtask\n{title}\n\n"
            "## Description\n{description}\n\n"
            "## Files Likely Affected\n{files}\n\n"
            "## Previous Changes in This Session\n{prev}\n\n"
            "## Instructions\n"
            "1. Implement the subtask as described — do NOT ask questions, just implement\n"
            "2. Follow existing code patterns and style\n"
            "3. Add appropriate error handling\n"
            "4. Write or update tests if applicable\n"
            "5. Commit changes with a descriptive message\n"
            "6. If the task is ambiguous, use your best judgment and proceed"
        ),
    },
    {
        "agent_name": "reviewer",
        "display_name": "Reviewer",
        "description": "Code review agent",
        "is_system": True,
        "system_prompt": (
            "You are a senior code reviewer. Review changes for correctness, quality, "
            "error handling, security, and performance."
        ),
        "user_prompt_template": (
            "## Task Context\nTitle: {title}\nDescription: {description}\n\n"
            "## Files Changed\n{files_changed}\n\n"
            "## Diff\n```diff\n{diff_text}\n```\n\n"
            "## Review Criteria\n"
            "1. Code correctness - does it implement the requirement?\n"
            "2. Code quality - is it readable, maintainable?\n"
            "3. Error handling - are edge cases covered?\n"
            "4. Security - any vulnerabilities introduced?\n"
            "5. Performance - any obvious inefficiencies?\n\n"
            "Respond in JSON format:\n"
            '{{\n  "approved": true,\n'
            '  "issues": [\n'
            '    {{"severity": "critical|major|minor", "file": "...", '
            '"line": 0, "description": "..."}}\n'
            "  ],\n"
            '  "suggestions": ["..."]\n}}'
        ),
    },
]


async def seed_role_configs(db: AsyncSession) -> None:
    """Insert or update system role configs (planner/coder/reviewer)."""
    created = 0
    updated = 0
    for defaults in DEFAULT_ROLE_CONFIGS:
        result = await db.execute(
            select(RoleConfig).where(RoleConfig.agent_name == defaults["agent_name"])
        )
        existing = result.scalar_one_or_none()
        if existing:
            # Update system configs if prompts have changed
            if not existing.is_system:
                continue
            changed = False
            for field in ("system_prompt", "user_prompt_template"):
                new_val = defaults.get(field)
                if new_val and getattr(existing, field) != new_val:
                    setattr(existing, field, new_val)
                    changed = True
            if changed:
                updated += 1
            continue
        db.add(RoleConfig(**defaults))
        created += 1
    await db.commit()
    if created or updated:
        logger.info("Seeded role configs: %d created, %d updated", created, updated)