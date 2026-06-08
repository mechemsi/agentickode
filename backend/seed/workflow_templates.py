# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Seed data for pipeline workflow templates."""

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun, WorkflowTemplate

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


DEFAULT_IMPLEMENT_PROMPT = (
    "Task: {{run.title}}\n\n"
    "{{run.description}}\n\n"
    "Implement this task end-to-end. When you're done:\n"
    "  1. Stage and commit all your changes with a clear conventional commit\n"
    "     message (`feat:`, `fix:`, `chore:` …).\n"
    "  2. Push the feature branch to `origin`.\n"
    "  3. Create a pull request (or merge request) using `gh pr create`\n"
    "     (GitHub), `glab mr create` (GitLab), or the equivalent for the\n"
    "     project's git provider. The PR description must summarize what\n"
    "     you changed and why.\n"
    "\n"
    "Always create a PR/MR — do not leave changes uncommitted or unpushed.\n"
    "If the PR creation fails, surface the exact error and stop; the\n"
    "approval step will handle re-trying through the platform's git\n"
    "provider integration."
)


DEFAULT_WORKFLOW_TEMPLATES: list[dict] = [
    {
        "name": "default",
        "description": (
            "Setup workspace (idempotent) → init feature branch in a worktree → "
            "agent implements + creates PR/MR → human review (chat with the agent "
            "if needed) → finalization closes the run once the PR is merged."
        ),
        "is_default": True,
        "is_system": True,
        "label_rules": [],
        "phases": [
            _phase(
                "workspace_setup",
                kind="legacy_phase",
                params={"workspace_strategy": "worktree"},
            ),
            _phase("init", kind="legacy_phase"),
            _phase(
                "implement",
                kind="agent",
                params={"prompt": DEFAULT_IMPLEMENT_PROMPT, "mode": "task"},
                uses_agent=True,
                timeout_seconds=3600,
            ),
            _phase(
                "approval",
                kind="legacy_phase",
                trigger_mode="wait_for_approval",
            ),
            _phase("finalization", kind="legacy_phase"),
        ],
    },
    {
        "name": "example-composable",
        "description": (
            "Example template demonstrating composable bash + agent steps "
            "(ADR-007). Manual-trigger only; not matched by any label."
        ),
        "is_default": False,
        "is_system": True,
        "label_rules": [],
        "phases": [
            _phase("workspace_setup", kind="legacy_phase"),
            _phase("init", kind="legacy_phase"),
            _phase(
                "build",
                kind="bash",
                params={"command": "make build"},
                timeout_seconds=600,
            ),
            _phase(
                "implement",
                kind="agent",
                role="coder",
                params={
                    "prompt": "Implement the task: {{run.title}}\n\n{{run.description}}",
                    "mode": "task",
                },
                uses_agent=True,
            ),
            _phase(
                "deploy",
                kind="bash",
                params={"command": "echo deploying && ./scripts/deploy.sh"},
                failure_mode="skip",
            ),
        ],
    },
    {
        "name": "pr-review",
        "description": (
            "AI code review for pull requests. Fetches the PR diff via the git "
            "provider API, runs a single-pass AI review, and posts the result as a "
            "comment on the PR. Triggered by the 'ai-review' label on a PR (GitHub / "
            "Gitea) or the POST /api/webhooks/pr-review endpoint (CI)."
        ),
        "is_default": False,
        "is_system": True,
        "label_rules": [],
        "triggers": [
            {
                "type": "pr_event",
                "source": "github",
                "action": "any",
                "label_filter": ["ai-review"],
            },
            {"type": "pr_event", "source": "gitea", "action": "any", "label_filter": ["ai-review"]},
        ],
        "phases": [
            _phase("pr_fetch", kind="legacy_phase"),
            _phase(
                "reviewing",
                kind="legacy_phase",
                uses_agent=True,
                agent_mode="generate",
                params={"review_strictness": "critical_only"},
            ),
            _phase("finalization", kind="legacy_phase"),
        ],
    },
]


_BACKFILL_KEYS = ("cli_flags", "environment_vars", "command_templates", "uses_agent", "agent_mode")


# System templates we used to seed but no longer do. ``seed_workflow_templates``
# deletes any row whose name is in this set when ``is_system=True``. Operators
# who customized these templates by hand (still under the same name) will also
# see them deleted — they opted into the system rename by keeping the name.
_DEPRECATED_SYSTEM_TEMPLATES = (
    "planner",
    "hotfix",
    "small-task",
    "fix-pr",
)


# Pre-v0.5.2 ``default`` template — used to detect "still the system
# version" so we can upgrade it to the new 5-step shape without
# clobbering user edits. Order matters; phase_names must match exactly.
_LEGACY_DEFAULT_PHASE_NAMES = (
    "workspace_setup",
    "init",
    "planning",
    "coding",
    "testing",
    "reviewing",
    "approval",
    "finalization",
)


def _looks_like_legacy_default(phases: list[dict]) -> bool:
    """Return True if ``phases`` matches the pre-v0.5.2 default shape.

    We only check phase_names + length; if the operator added/removed
    or even just renamed a phase, this returns False and the row is
    left alone.
    """
    if len(phases) != len(_LEGACY_DEFAULT_PHASE_NAMES):
        return False
    return all(
        p.get("phase_name") == expected
        for p, expected in zip(phases, _LEGACY_DEFAULT_PHASE_NAMES, strict=False)
    )


async def seed_workflow_templates(db: AsyncSession) -> None:
    """Insert all system workflow templates if they don't exist.

    Also:
    - Backfills new phase_config keys into existing system templates so
      upgrades pick up the fields in their JSONB without overwriting
      user edits.
    - Upgrades the ``default`` template from the pre-v0.5.2 8-phase
      shape to the new simplified 5-step shape when it hasn't been
      edited by the operator.
    - Deletes deprecated system templates (``_DEPRECATED_SYSTEM_TEMPLATES``)
      from existing DBs so the seed and the DB stay in sync.
    """
    # Step 0: prune deprecated system templates. Only ``is_system=True``
    # rows are touched — operator-created templates with the same name
    # are left alone. Historic ``task_runs`` rows referencing these
    # templates get their FK NULLed so the cascade doesn't fail (the
    # column is nullable and the FK has no ON DELETE clause).
    deprecated_result = await db.execute(
        select(WorkflowTemplate).where(
            WorkflowTemplate.name.in_(_DEPRECATED_SYSTEM_TEMPLATES),
            WorkflowTemplate.is_system.is_(True),
        )
    )
    deleted_names: list[str] = []
    for row in deprecated_result.scalars().all():
        await db.execute(
            update(TaskRun)
            .where(TaskRun.workflow_template_id == row.id)
            .values(workflow_template_id=None)
        )
        deleted_names.append(row.name)
        await db.delete(row)
    if deleted_names:
        logger.info(
            "Removed deprecated system workflow templates: %s",
            ", ".join(sorted(deleted_names)),
        )

    created = 0
    backfilled = 0
    reconciled = 0
    upgraded_default = False
    for defaults in DEFAULT_WORKFLOW_TEMPLATES:
        result = await db.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.name == defaults["name"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            db.add(WorkflowTemplate(**defaults))
            created += 1
            continue

        if not existing.is_system:
            continue

        # Special case: replace the legacy 8-phase "default" with the
        # new 5-step shape, but only when it's still the unmodified
        # system version (otherwise we'd stomp on operator edits).
        if defaults["name"] == "default" and _looks_like_legacy_default(existing.phases or []):
            existing.phases = defaults["phases"]
            existing.description = defaults["description"]
            upgraded_default = True
            continue

        # Reconcile routing-critical fields for system templates that declare
        # triggers (currently pr-review). Existing-DB rows that predate this
        # release can carry stale triggers (e.g. label-type entries backfilled
        # from old label_rules) that ``TriggerMatcher`` will never match for a
        # pr_event — silently killing the feature. System rows are seed-managed,
        # so re-sync them from the seed definition. Operator-owned (is_system=
        # False) rows are already skipped above and never touched.
        declared_triggers = defaults.get("triggers")
        if declared_triggers is not None and existing.triggers != declared_triggers:
            existing.triggers = declared_triggers
            existing.phases = defaults["phases"]
            existing.description = defaults["description"]
            reconciled += 1
            continue

        # Backfill missing keys into existing system templates
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
    if reconciled:
        logger.info("Reconciled triggers/phases for %d system workflow templates", reconciled)
    if upgraded_default:
        logger.info("Upgraded the system 'default' template to the new 5-step shape")
