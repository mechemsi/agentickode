# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Rules dispatcher — listens to broadcaster events and feeds them to the rules engine."""

import asyncio
import logging

from backend.database import async_session
from backend.services.rules_engine import AutomationEvent, RulesEngine
from backend.worker.broadcaster import broadcaster

logger = logging.getLogger("agentickode.rules_dispatcher")

# Broadcaster event types that can trigger automation rules
_TRIGGERABLE_EVENTS = {
    "run_started",
    "run_completed",
    "run_failed",
    "phase_completed",
    "phase_failed",
    "phase_waiting",
    "approval_requested",
    "cost_threshold_exceeded",
}


class RulesDispatcher:
    """Subscribe to broadcaster global events and evaluate automation rules."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._engine = RulesEngine()
        self._bg_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
            logger.info("Rules dispatcher started")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Rules dispatcher stopped")

    async def _run(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()  # type: ignore[type-arg]
        broadcaster.subscribe_global(queue)
        try:
            while True:
                payload = await queue.get()
                event_type = payload.get("type", "")
                if event_type not in _TRIGGERABLE_EVENTS:
                    continue
                task = asyncio.create_task(self._evaluate(event_type, payload))
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe_global(queue)

    async def _evaluate(self, event_type: str, payload: dict) -> None:
        """Evaluate all rules for a single event."""
        try:
            event = AutomationEvent(
                source="run_event",
                event_type=event_type,
                project_id=payload.get("project_id"),
                run_id=payload.get("run_id"),
                data=payload,
            )
            async with async_session() as session:
                matched = await self._engine.evaluate(event, session)
                for rule in matched:
                    await self._engine.execute(rule, event, session)
                await session.commit()
        except Exception:
            logger.exception("Rules evaluation failed for event %s", event_type)
