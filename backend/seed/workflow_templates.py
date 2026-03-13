# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Seed data for pipeline workflow templates."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import WorkflowTemplate

logger = logging.getLogger("agentickode.seed")

_PHASE_AUTO = {
    "role": None,
    "params": {},
    "enabled": True,
    "trigger_mode": "auto",
    "notify_source": False,
    "uses_agent": None,
    "agent_mode": None,
    "timeout_seconds": None,
    "cli_flags": None,
    "environment_vars": None,
    "command_templates": None,
}


def _phase(name: str, **overrides: object) -> dict:
    return {**_PHASE_AUTO, "phase_name": name, **overrides}


DEFAULT_WORKFLOW_TEMPLATES: list[dict] = [
    {
        "name": "default",
        "description": "Full end-to-end AI task workflow",
        "is_default": True,
        "is_system": True,
        "label_rules": [],
        "phases": [
            _phase("workspace_setup"),
            _phase("init"),
            _phase("planning", uses_agent=True),
            _phase("coding", uses_agent=True),
            _phase("testing"),
            _phase("reviewing", uses_agent=True),
            _phase("approval", trigger_mode="wait_for_approval"),
            _phase("finalization"),
        ],
    },
    {
        "name": "planner",
        "description": "Analyze task and decompose into subtasks",
        "is_default": False,
        "is_system": True,
        "label_rules": [{"match_all": [], "match_any": ["plan-only", "decompose"]}],
        "phases": [
            _phase("workspace_setup"),
            _phase("init"),
            _phase("planning", uses_agent=True),
            _phase("task_creation"),
            _phase("finalization"),
        ],
    },
    {
        "name": "hotfix",
        "description": "Quick coding without planning phase",
        "is_default": False,
        "is_system": True,
        "label_rules": [{"match_all": [], "match_any": ["hotfix", "quick-fix"]}],
        "phases": [
            _phase("workspace_setup"),
            _phase("init"),
            _phase("coding", uses_agent=True),
            _phase("testing"),
            _phase("reviewing", uses_agent=True),
            _phase("approval", trigger_mode="wait_for_approval"),
            _phase("finalization"),
        ],
    },
    {
        "name": "small-task",
        "description": "Execute a pre-planned subtask (child of planner)",
        "is_default": False,
        "is_system": True,
        "label_rules": [{"match_all": [], "match_any": ["subtask"]}],
        "phases": [
            _phase("workspace_setup"),
            _phase("init"),
            _phase("coding", uses_agent=True),
            _phase("testing"),
            _phase("reviewing", uses_agent=True),
            _phase("approval", trigger_mode="wait_for_approval"),
            _phase("finalization"),
        ],
    },
    {
        "name": "pr-review",
        "description": "Review an existing PR/MR via API",
        "is_default": False,
        "is_system": True,
        "label_rules": [{"match_all": [], "match_any": ["review-pr", "pr-review"]}],
        "phases": [
            _phase("pr_fetch"),
            _phase("reviewing", uses_agent=True),
            _phase("finalization"),
        ],
    },
    {
        "name": "fix-pr",
        "description": "Fix code after PR review feedback",
        "is_default": False,
        "is_system": True,
        "label_rules": [{"match_all": [], "match_any": ["fix-pr", "pr-fix"]}],
        "phases": [
            _phase("pr_fetch"),
            _phase("workspace_setup"),
            _phase("init"),
            _phase("coding", uses_agent=True),
            _phase("reviewing", uses_agent=True),
            _phase("finalization"),
        ],
    },
]


_BACKFILL_KEYS = ("cli_flags", "environment_vars", "command_templates", "uses_agent", "agent_mode")


async def seed_workflow_templates(db: AsyncSession) -> None:
    """Insert all system workflow templates if they don't exist.

    Also backfills new phase_config keys into existing system templates
    so upgrades get the fields in their JSONB without overwriting user edits.
    """
    created = 0
    backfilled = 0
    for defaults in DEFAULT_WORKFLOW_TEMPLATES:
        result = await db.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.name == defaults["name"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            db.add(WorkflowTemplate(**defaults))
            created += 1
            continue

        # Backfill missing keys into existing system templates
        if not existing.is_system:
            continue
        phases: list[dict] = existing.phases or []  # type: ignore[assignment]
        changed = False
        for phase in phases:
            for key in _BACKFILL_KEYS:
                if key not in phase:
                    phase[key] = None
                    changed = True
        if changed:
            existing.phases = list(phases)  # type: ignore[assignment]  # trigger dirty
            backfilled += 1

    await db.commit()
    if created:
        logger.info("Seeded %d workflow templates", created)
    if backfilled:
        logger.info("Backfilled phase_config fields for %d workflow templates", backfilled)
