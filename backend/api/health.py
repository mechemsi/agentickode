# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Health and stats endpoints."""

import asyncio
import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.repositories.ollama_server_repo import OllamaServerRepository
from backend.repositories.task_run_repo import TaskRunRepository
from backend.services.http_client import get_http_client
from backend.services.openhands_service import OpenHandsService

router = APIRouter(tags=["health"])


async def _check_service(name: str, check_fn) -> dict:
    t0 = time.monotonic()
    try:
        ok = await check_fn()
        latency = round((time.monotonic() - t0) * 1000, 1)
        return {"name": name, "status": "ok" if ok else "error", "latency_ms": latency}
    except Exception as e:
        latency = round((time.monotonic() - t0) * 1000, 1)
        return {"name": name, "status": "error", "latency_ms": latency, "error": str(e)}


async def _check_db(db: AsyncSession) -> bool:
    from sqlalchemy import text

    await db.execute(text("SELECT 1"))
    return True


async def _check_ollama_server(url: str) -> bool:
    client = get_http_client()
    resp = await client.get(f"{url.rstrip('/')}/api/tags", timeout=5.0)
    return resp.status_code == 200


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    repo = TaskRunRepository(db)
    ollama_repo = OllamaServerRepository(db)

    services: list[dict] = []

    # Database check
    services.append(await _check_service("database", lambda: _check_db(db)))

    # Ollama: check all configured servers from DB
    ollama_servers = await ollama_repo.list_all()
    if not ollama_servers:
        services.append({"name": "ollama", "status": "not_configured", "latency_ms": None})
    else:
        checks = [
            _check_service(
                f"ollama:{server.name}",
                lambda url=server.url: _check_ollama_server(url),
            )
            for server in ollama_servers
        ]
        results = await asyncio.gather(*checks)
        services.extend(results)

    # OpenHands: only check if configured
    if settings.openhands_url:
        openhands = OpenHandsService(get_http_client())
        services.append(await _check_service("openhands", openhands.is_healthy))

    all_ok = all(s["status"] in ("ok", "not_configured") for s in services)
    active = await repo.get_active_count()

    return {
        "status": "ok" if all_ok else "degraded",
        "services": services,
        "worker_running": True,
        "active_runs": active,
    }