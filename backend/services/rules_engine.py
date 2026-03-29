# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Rules engine — evaluate automation rules against events and execute actions."""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.automation_rules import AutomationRule
from backend.repositories.automation_rule_repo import AutomationRuleRepository
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.services.run_factory import create_task_run

logger = logging.getLogger("agentickode.rules_engine")


@dataclass
class AutomationEvent:
    """An event that can trigger automation rules."""

    source: str  # run_event, webhook, monitoring, schedule, notification
    event_type: str  # run_completed, run_failed, phase_completed, etc.
    project_id: str | None = None
    run_id: int | None = None
    data: dict = field(default_factory=dict)


class RulesEngine:
    """Match events against automation rules and execute configured actions."""

    async def evaluate(self, event: AutomationEvent, session: AsyncSession) -> list[AutomationRule]:
        """Find all matching enabled rules for the given event."""
        repo = AutomationRuleRepository(session)
        all_rules = await repo.list_enabled()

        matched = []
        for rule in all_rules:
            if self._matches(rule, event):
                matched.append(rule)
        return matched

    async def execute(
        self, rule: AutomationRule, event: AutomationEvent, session: AsyncSession
    ) -> bool:
        """Execute a matched rule's action. Returns True if action was taken."""
        if not self._check_cooldown(rule):
            logger.debug("Rule %d skipped (cooldown)", rule.id)
            return False

        try:
            if rule.action_type == "create_run":
                await self._action_create_run(rule, event, session)
            elif rule.action_type == "send_to_session":
                await self._action_send_to_session(rule, event, session)
            elif rule.action_type == "notify":
                logger.info("Rule %d: notify action (not yet implemented)", rule.id)
            elif rule.action_type == "send_message":
                logger.info("Rule %d: send_message action (not yet implemented)", rule.id)
            else:
                logger.warning("Rule %d: unknown action_type %s", rule.id, rule.action_type)
                return False

            rule.last_triggered_at = datetime.now(UTC)
            rule.trigger_count = (rule.trigger_count or 0) + 1
            return True
        except Exception:
            logger.exception("Rule %d action failed", rule.id)
            return False

    def _matches(self, rule: AutomationRule, event: AutomationEvent) -> bool:
        """Check if an event matches a rule's source and filter criteria."""
        if rule.event_source != event.source:
            return False

        if rule.project_id and rule.project_id != event.project_id:
            return False

        event_filter = rule.event_filter or {}
        for key, expected in event_filter.items():
            if (key == "event_type" and event.event_type != expected) or (
                key != "event_type" and event.data.get(key) != expected
            ):
                return False

        return True

    def _check_cooldown(self, rule: AutomationRule) -> bool:
        """Return True if enough time has passed since last trigger."""
        if not rule.last_triggered_at:
            return True
        elapsed = (datetime.now(UTC) - rule.last_triggered_at).total_seconds()
        return elapsed >= (rule.cooldown_seconds or 0)

    async def _action_create_run(
        self, rule: AutomationRule, event: AutomationEvent, session: AsyncSession
    ) -> None:
        """Create a TaskRun from rule's action_config."""
        config = rule.action_config or {}
        project_id = config.get("project_id") or rule.project_id or event.project_id
        if not project_id:
            logger.warning("Rule %d: no project_id for create_run action", rule.id)
            return

        project_repo = ProjectConfigRepository(session)
        project = await project_repo.get_by_id(project_id)
        if not project:
            logger.warning("Rule %d: project %s not found", rule.id, project_id)
            return

        task_id = f"rule-{rule.id}-{uuid.uuid4().hex[:8]}"
        title = config.get("title", f"[Auto] {rule.name}")
        description = config.get("description", rule.description or "")

        # Inject event data into description if template has placeholders
        if "{event_type}" in description:
            description = description.replace("{event_type}", event.event_type)
        if "{run_id}" in description:
            description = description.replace("{run_id}", str(event.run_id or ""))

        run = create_task_run(
            task_id=task_id,
            project=project,
            title=title,
            description=description,
            task_source="automation",
            task_source_meta={
                "automation_rule_id": rule.id,
                "automation_rule_name": rule.name,
                "trigger_event": event.event_type,
                "trigger_source": event.source,
            },
        )
        session.add(run)
        logger.info("Rule %d dispatched run for '%s'", rule.id, title)

    async def _action_send_to_session(
        self, rule: AutomationRule, event: AutomationEvent, session: AsyncSession
    ) -> None:
        """Send a command to a local terminal tmux session."""
        config = rule.action_config or {}
        tmux_name = config.get("tmux_name")
        message = config.get("message", "")

        if not tmux_name or not message:
            logger.warning("Rule %d: send_to_session needs tmux_name and message", rule.id)
            return

        # Inject event data into message
        if "{event_type}" in message:
            message = message.replace("{event_type}", event.event_type)
        if "{run_id}" in message:
            message = message.replace("{run_id}", str(event.run_id or ""))
        if "{project_id}" in message:
            message = message.replace("{project_id}", event.project_id or "")

        env = {
            **os.environ,
            "PATH": f"/root/.local/bin:/root/.local/share/claude/bin:{os.environ.get('PATH', '')}",
        }

        # Check tmux session exists
        check = await asyncio.create_subprocess_shell(
            f"tmux has-session -t {tmux_name} 2>/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await check.wait()
        if check.returncode != 0:
            logger.warning("Rule %d: tmux session %s not found", rule.id, tmux_name)
            return

        # Send keys to tmux
        escaped = message.replace("'", "'\\''")
        await asyncio.create_subprocess_shell(
            f"tmux send-keys -t {tmux_name} '{escaped}' Enter",
            env=env,
        )
        logger.info("Rule %d: sent message to session %s", rule.id, tmux_name)
