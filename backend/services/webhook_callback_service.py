# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Fires HTTP POST to registered webhook callback URLs for a run."""

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import WebhookCallback

logger = logging.getLogger("autodev.webhook_callbacks")


class WebhookCallbackService:
    """Fires webhook callbacks registered for a specific run."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def fire(
        self,
        session: AsyncSession,
        run_id: int,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        """Send event payload to all active webhooks matching this event."""
        result = await session.execute(
            select(WebhookCallback).where(
                WebhookCallback.run_id == run_id,
                WebhookCallback.active.is_(True),
            )
        )
        callbacks = list(result.scalars().all())

        for cb in callbacks:
            events = cb.events or []
            if events and event not in events:
                continue

            try:
                raw_headers = cb.headers or {}
                headers: dict[str, str] = {str(k): str(v) for k, v in raw_headers.items()}
                headers.setdefault("Content-Type", "application/json")
                body = {
                    "event": event,
                    "run_id": run_id,
                    **payload,
                }
                resp = await self._client.post(cb.url, json=body, headers=headers, timeout=10)
                if resp.status_code >= 400:
                    logger.warning(
                        "Webhook %s returned %s for event %s",
                        cb.url,
                        resp.status_code,
                        event,
                    )
            except Exception:
                logger.warning(
                    "Failed to fire webhook %s for event %s",
                    cb.url,
                    event,
                    exc_info=True,
                )