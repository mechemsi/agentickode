# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Seed data for per-CLI-agent prompt overrides."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import RoleConfig
from backend.models.agents import RolePromptOverride

logger = logging.getLogger("autodev.seed")

_AUTONOMOUS_DIRECTIVE = (
    "IMPORTANT: You are running autonomously. Do NOT ask clarifying questions. "
    "Make your best judgment and implement the changes directly. "
    "If the task is ambiguous, proceed with the most reasonable interpretation."
)

AGENT_PROMPT_OVERRIDES: dict[str, dict] = {
    "claude": {"minimal_mode": True},
    "aider": {
        "minimal_mode": False,
        "system_prompt": (
            "You are an AI coding assistant using Aider. "
            f"{_AUTONOMOUS_DIRECTIVE}\n\n"
            "Work file-by-file. For each file, state the path, then show the changes. "
            "Commit each logical change with a descriptive message."
        ),
        "user_prompt_template": (
            "## Task\n{title}\n\n## Description\n{description}\n\n"
            "## Files Likely Affected\n{files}\n\n"
            "## Previous Changes\n{prev}\n\n"
            "Work through each file methodically. "
            "Use /add to include files before editing. "
            "Do NOT ask questions — implement directly."
        ),
    },
    "codex": {
        "minimal_mode": False,
        "system_prompt": (
            "You are a code generation assistant. "
            f"{_AUTONOMOUS_DIRECTIVE}\n\n"
            "Output code changes only. No explanations unless asked."
        ),
        "user_prompt_template": (
            "Task: {title}\n\n{description}\n\n"
            "Files: {files}\n\nPrevious changes: {prev}\n\n"
            "Write the code changes needed. Do NOT ask questions."
        ),
    },
    "gemini-cli": {
        "minimal_mode": False,
        "system_prompt": (
            "You are an AI coding assistant. "
            f"{_AUTONOMOUS_DIRECTIVE}\n\n"
            "Respect existing code style and patterns. "
            "Implement changes directly without asking for clarification."
        ),
        "user_prompt_template": (
            "## Context\nYou are working on a software project.\n\n"
            "## Task\nTitle: {title}\nDescription: {description}\n\n"
            "## Files Likely Affected\n{files}\n\n"
            "## Previous Changes\n{prev}\n\n"
            "## Constraints\n"
            "- Follow existing code patterns\n"
            "- Add error handling\n"
            "- Write tests if applicable\n"
            "- Do NOT ask questions — implement directly"
        ),
    },
    "kimi": {
        "minimal_mode": False,
        "system_prompt": (
            "You are an AI coding assistant. "
            f"{_AUTONOMOUS_DIRECTIVE}\n\n"
            "Respect existing code style and patterns. "
            "Implement changes directly without asking for clarification."
        ),
        "user_prompt_template": (
            "## Context\nYou are working on a software project.\n\n"
            "## Task\nTitle: {title}\nDescription: {description}\n\n"
            "## Files Likely Affected\n{files}\n\n"
            "## Previous Changes\n{prev}\n\n"
            "## Requirements\n"
            "- Follow existing code patterns\n"
            "- Add error handling\n"
            "- Write tests if applicable\n"
            "- Do NOT ask questions — implement directly"
        ),
    },
}


async def seed_prompt_overrides(db: AsyncSession) -> None:
    """Insert or update prompt overrides for each system role config.

    Creates/updates overrides for known CLI agents (claude, aider, codex, etc.)
    on each system config (planner, coder, reviewer).
    """
    created = 0
    updated = 0
    result = await db.execute(select(RoleConfig).where(RoleConfig.is_system.is_(True)))
    system_configs = result.scalars().all()

    for config in system_configs:
        for cli_agent_name, defaults in AGENT_PROMPT_OVERRIDES.items():
            result = await db.execute(
                select(RolePromptOverride).where(
                    RolePromptOverride.role_config_id == config.id,
                    RolePromptOverride.cli_agent_name == cli_agent_name,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                changed = False
                for field in ("system_prompt", "user_prompt_template", "minimal_mode"):
                    new_val = defaults.get(field)
                    if new_val is not None and getattr(existing, field) != new_val:
                        setattr(existing, field, new_val)
                        changed = True
                if changed:
                    updated += 1
                continue
            override = RolePromptOverride(
                role_config_id=config.id,
                cli_agent_name=cli_agent_name,
                system_prompt=defaults.get("system_prompt"),
                user_prompt_template=defaults.get("user_prompt_template"),
                minimal_mode=defaults.get("minimal_mode", False),
                extra_params=defaults.get("extra_params", {}),
            )
            db.add(override)
            created += 1
    await db.commit()
    if created or updated:
        logger.info("Seeded prompt overrides: %d created, %d updated", created, updated)