# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Redis-backed task queue with per-server concurrency control."""

import logging
from datetime import UTC, datetime

import redis.asyncio as redis

from backend.config import settings

logger = logging.getLogger("agentickode.queue")


class QueueService:
    """Thin Redis wrapper for task run queuing and server lock management."""

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        await self._redis.ping()
        logger.info("Redis queue connected")

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    @property
    def client(self) -> redis.Redis:
        assert self._redis is not None, "QueueService not connected"
        return self._redis

    # --- Server concurrency tracking ---

    async def get_server_active_count(self, server_id: int) -> int:
        """Count active runs on a server."""
        return await self.client.scard(f"server:{server_id}:active_runs")

    async def acquire_server_slot(self, server_id: int, run_id: int) -> bool:
        """Try to claim a slot on the server. Returns True if acquired."""
        key = f"server:{server_id}:active_runs"
        await self.client.sadd(key, str(run_id))
        return True

    async def release_server_slot(self, server_id: int, run_id: int) -> None:
        """Release a slot when run completes."""
        await self.client.srem(f"server:{server_id}:active_runs", str(run_id))

    # --- Run state tracking ---

    async def mark_run_started(self, run_id: int, server_id: int) -> None:
        """Record that a run has started on a server."""
        await self.client.hset(
            f"run:{run_id}",
            mapping={
                "server_id": str(server_id),
                "started_at": datetime.now(UTC).isoformat(),
                "status": "running",
            },
        )
        await self.acquire_server_slot(server_id, run_id)

    async def mark_run_completed(self, run_id: int, server_id: int | None = None) -> None:
        """Record run completion and release server slot."""
        if server_id is None:
            data = await self.client.hgetall(f"run:{run_id}")
            server_id = int(data.get("server_id", 0)) if data else 0
        if server_id:
            await self.release_server_slot(server_id, run_id)
        await self.client.delete(f"run:{run_id}")

    async def get_queue_status(self) -> dict:
        """Get overview of queue state."""
        keys: list[str] = []
        async for key in self.client.scan_iter("server:*:active_runs"):
            keys.append(key)
        server_loads: dict[str, int] = {}
        for key in keys:
            sid = key.split(":")[1]
            count: int = await self.client.scard(key)
            if count > 0:
                server_loads[sid] = count
        return {"server_loads": server_loads}

    async def cleanup_stale_entries(self, valid_run_ids: set[int]) -> None:
        """Remove Redis entries for runs that are no longer active in DB."""
        async for key in self.client.scan_iter("server:*:active_runs"):
            members = await self.client.smembers(key)
            for member in members:
                if int(member) not in valid_run_ids:
                    await self.client.srem(key, member)
                    logger.info("Cleaned stale run %s from %s", member, key)


# Singleton
queue_service = QueueService()
