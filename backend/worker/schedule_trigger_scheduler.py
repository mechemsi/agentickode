# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Background scheduler that fires WorkflowTemplate ScheduleTrigger entries.

Polls workflow_templates for triggers of type ``schedule``, evaluates each
cron against the last tick window, and dispatches a TaskRun bound to the
matching template via ``TriggerMatcher`` (so all routing goes through one
choke point).

Notes:
* Each template can have multiple schedule triggers; each fires independently.
* A ``project_id`` is required to create a TaskRun. The scheduler reads it
  from the top-level ``project_id`` field on the schedule trigger entry
  (matching the ``ScheduleTrigger`` Pydantic schema); if absent, the trigger
  is skipped with a debug log — we don't pick an arbitrary project.
* The scheduler tracks per-trigger last-fire times in-process so a single
  cron tick can't double-fire even if ``_tick`` is invoked twice within the
  same minute (e.g. on startup catch-up).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models import ProjectConfig, WorkflowTemplate
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.services.cron_parser import next_occurrence
from backend.services.run_factory import create_task_run
from backend.services.triggers import TriggerEvent, TriggerMatcher

logger = logging.getLogger("agentickode.schedule_trigger_scheduler")


class ScheduleTriggerScheduler:
    """Polls WorkflowTemplate.triggers for ``schedule`` entries and fires them."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        poll_seconds: int = 30,
    ):
        self._session_factory = session_factory
        self._poll_seconds = poll_seconds
        self._running = False
        # In-memory dedup: (template_id, cron_expr) -> last_fired_at
        self._last_fired: dict[tuple[int, str], datetime] = {}

    async def run(self) -> None:
        self._running = True
        logger.info("ScheduleTriggerScheduler started (poll=%ds)", self._poll_seconds)
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("ScheduleTriggerScheduler tick failed")
            await asyncio.sleep(self._poll_seconds)

    def stop(self) -> None:
        self._running = False
        logger.info("ScheduleTriggerScheduler stopping")

    async def _tick(self) -> None:
        """One poll cycle: find due schedule triggers and dispatch them."""
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            templates = await self._templates_with_schedules(session)
            for template in templates:
                for trigger in template.triggers or []:
                    if trigger.get("type") != "schedule":
                        continue
                    cron = trigger.get("cron")
                    if not isinstance(cron, str) or not cron.strip():
                        continue
                    if not self._is_due(template.id, cron, now):
                        continue
                    await self._dispatch(template, trigger, session)
            await session.commit()

    @staticmethod
    async def _templates_with_schedules(session: AsyncSession) -> list[WorkflowTemplate]:
        """Load every template (filtering by JSON content varies across dialects)."""
        result = await session.execute(select(WorkflowTemplate))
        templates = list(result.scalars().all())
        return [
            t
            for t in templates
            if any((entry or {}).get("type") == "schedule" for entry in (t.triggers or []))
        ]

    def _is_due(self, template_id: int, cron: str, now: datetime) -> bool:
        """Return True iff this cron's next fire time has elapsed since last seen.

        Compares the cron's next-after-last-fire timestamp against ``now``. If
        we've never fired this template+cron pair, prime the bookkeeping with
        the next future occurrence to avoid back-firing on first boot.
        """
        key = (template_id, cron)
        last = self._last_fired.get(key)
        if last is None:
            # First time seeing this trigger — don't fire retroactively. Just
            # record a starting point one poll window in the past so the first
            # genuine tick fires.
            self._last_fired[key] = now - timedelta(seconds=self._poll_seconds + 1)
            last = self._last_fired[key]

        try:
            due_at = next_occurrence(cron, last)
        except Exception:
            logger.warning("Invalid cron %r on template %d, skipping", cron, template_id)
            return False

        if due_at <= now:
            self._last_fired[key] = now
            return True
        return False

    async def _dispatch(
        self,
        template: WorkflowTemplate,
        trigger: dict,
        session: AsyncSession,
    ) -> None:
        """Create a TaskRun for a fired schedule trigger.

        Skips when no project can be resolved — schedule triggers without a
        project context are no-ops by design.
        """
        project_id = trigger.get("project_id")
        if not project_id:
            logger.debug(
                "Template %d schedule trigger has no project_id, skipping dispatch",
                template.id,
            )
            return

        project = await self._resolve_project(session, project_id)
        if project is None:
            logger.warning(
                "Template %d schedule trigger references unknown project %s",
                template.id,
                project_id,
            )
            return

        # Route through TriggerMatcher so dispatch precedence stays unified —
        # if the user added a more-specific schedule trigger to another
        # template with the same cron, the matcher honors that priority.
        # ``project_id`` is forwarded so cross-project cron collisions don't
        # bind the run to the wrong template.
        matched = await TriggerMatcher(session).match(
            TriggerEvent(
                type="schedule",
                source="cron",
                cron_tick=trigger.get("cron"),
                project_id=project_id,
            )
        )
        bind_to = matched or template

        task_id = f"sched-tpl-{template.id}-{uuid.uuid4().hex[:8]}"
        cron = trigger.get("cron", "")
        run = create_task_run(
            task_id=task_id,
            project=project,
            title=f"[Schedule] {template.name}",
            description=f"Triggered by cron '{cron}' on template '{template.name}'",
            task_source="schedule",
            task_source_meta={
                "schedule_cron": cron,
                "workflow_template_name": template.name,
            },
            workflow_template_id=bind_to.id,
        )
        session.add(run)
        await session.flush()

        try:
            next_at = next_occurrence(cron, datetime.now(UTC)).isoformat()
        except Exception:
            next_at = "unknown"
        logger.info(
            "Schedule trigger fired template=%s cron=%s -> run #%d (next: %s)",
            template.name,
            cron,
            run.id,
            next_at,
        )

    @staticmethod
    async def _resolve_project(session: AsyncSession, project_id: str) -> ProjectConfig | None:
        repo = ProjectConfigRepository(session)
        return await repo.get_by_id(project_id)
