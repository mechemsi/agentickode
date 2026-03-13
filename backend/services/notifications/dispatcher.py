# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Notification dispatcher — background task that listens to broadcaster events."""

import asyncio
import logging

from backend.database import async_session
from backend.repositories.notification_channel_repo import NotificationChannelRepository
from backend.services.http_client import get_http_client
from backend.services.notifications.formatter import format_notification
from backend.services.notifications.service import NotificationService
from backend.worker.broadcaster import broadcaster

logger = logging.getLogger("agentickode.notifications.dispatcher")

# Map broadcaster event types to notification event names
_EVENT_MAP: dict[str, str] = {
    "run_started": "run_started",
    "run_completed": "run_completed",
    "run_failed": "run_failed",
    "approval_requested": "approval_requested",
    "phase_completed": "phase_completed",
    "phase_failed": "phase_failed",
    "phase_waiting": "phase_waiting",
    "plan_review_requested": "plan_review_requested",
    "cost_threshold_exceeded": "cost_threshold_exceeded",
}


class NotificationDispatcher:
    """Subscribe to broadcaster global events and fan out to notification channels."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._bg_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
            logger.info("Notification dispatcher started")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Notification dispatcher stopped")

    async def _run(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()  # type: ignore[type-arg]
        broadcaster.subscribe_global(queue)
        try:
            while True:
                payload = await queue.get()
                event_type = payload.get("type", "")
                notification_event = _EVENT_MAP.get(event_type)
                if notification_event is None:
                    continue
                task = asyncio.create_task(self._dispatch(notification_event, payload))
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe_global(queue)

    async def _dispatch(self, event_type: str, data: dict) -> None:
        try:
            async with async_session() as session:
                repo = NotificationChannelRepository(session)
                channels = await repo.list_enabled()

            message = format_notification(event_type, data)
            client = get_http_client()
            service = NotificationService(client)

            tasks = []
            for ch in channels:
                if event_type in (ch.events or []):
                    tasks.append(self._send_safe(service, ch, message))
            if tasks:
                await asyncio.gather(*tasks)
        except Exception:
            logger.exception("Failed to dispatch notification for %s", event_type)

    async def _send_safe(self, service: NotificationService, channel, message: str) -> None:  # type: ignore[no-untyped-def]
        try:
            await service.send(channel, message)
        except Exception:
            logger.exception(
                "Failed to send to channel %s (%s)", channel.name, channel.channel_type
            )
