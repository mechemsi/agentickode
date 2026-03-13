# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Broadcaster — fan-out logs and events to WebSocket subscribers + DB.

Singleton used by phases to emit logs and by ws.py to subscribe clients.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from backend.database import async_session
from backend.models import TaskLog

logger = logging.getLogger("agentickode.broadcaster")

# Truncation limits for metadata fields
_MAX_PROMPT_CHARS = 10_000
_MAX_OUTPUT_CHARS = 2_000


def make_log_metadata(category: str, **kwargs: Any) -> dict[str, Any]:
    """Build a metadata dict with auto-truncation of large text fields.

    Categories: system_prompt, prompt, response, ssh_command
    """
    meta: dict[str, Any] = {"category": category}
    for key, value in kwargs.items():
        if isinstance(value, str):
            limit = (
                _MAX_PROMPT_CHARS
                if key in ("prompt_text", "system_prompt_text")
                else _MAX_OUTPUT_CHARS
            )
            if len(value) > limit:
                meta[key] = value[:limit]
                meta[f"{key}_truncated"] = True
                meta[f"{key}_original_length"] = len(value)
            else:
                meta[key] = value
        else:
            meta[key] = value
    return meta


class Broadcaster:
    def __init__(self):
        self._run_subs: dict[int, list[asyncio.Queue]] = {}
        self._global_subs: list[asyncio.Queue] = []

    # --- subscription management ---

    def subscribe_run(self, run_id: int, queue: asyncio.Queue):
        self._run_subs.setdefault(run_id, []).append(queue)

    def unsubscribe_run(self, run_id: int, queue: asyncio.Queue):
        if run_id in self._run_subs:
            self._run_subs[run_id] = [q for q in self._run_subs[run_id] if q is not queue]
            if not self._run_subs[run_id]:
                del self._run_subs[run_id]

    def subscribe_global(self, queue: asyncio.Queue):
        self._global_subs.append(queue)

    def unsubscribe_global(self, queue: asyncio.Queue):
        self._global_subs = [q for q in self._global_subs if q is not queue]

    # --- emitting ---

    async def log(
        self,
        run_id: int,
        message: str,
        level: str = "info",
        phase: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Write a log entry to DB and broadcast to run subscribers."""
        now = datetime.now(UTC)

        # Persist to DB
        async with async_session() as session:
            entry = TaskLog(
                run_id=run_id,
                timestamp=now,
                level=level,
                phase=phase,
                message=message,
                metadata_=metadata,
            )
            session.add(entry)
            await session.commit()

        # Broadcast to run subscribers
        payload: dict[str, Any] = {
            "type": "log",
            "run_id": run_id,
            "timestamp": now.isoformat(),
            "level": level,
            "phase": phase,
            "message": message,
        }
        if metadata is not None:
            payload["metadata_"] = metadata
        for q in self._run_subs.get(run_id, []):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(payload)

    async def event(self, run_id: int, event_type: str, data: dict | None = None):
        """Broadcast a global event (status change, phase change, etc.)."""
        payload = {
            "type": event_type,
            "run_id": run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **(data or {}),
        }
        for q in self._global_subs:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(payload)


# Singleton
broadcaster = Broadcaster()
