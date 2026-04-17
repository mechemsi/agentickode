# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Seed the built-in 'platform' workspace server (local execution)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import DiscoveredAgent, WorkspaceServer
from backend.services.workspace.agent_discovery import AgentDiscoveryService
from backend.services.workspace.local_command_service import LocalCommandService

logger = logging.getLogger("agentickode.seed")


async def seed_platform_server(db: AsyncSession) -> None:
    """Ensure the local platform workspace server exists and agents are discovered.

    This server lets the platform execute tasks directly (via subprocess)
    without needing an external SSH-based workspace server.
    """
    result = await db.execute(
        select(WorkspaceServer).where(WorkspaceServer.server_type == "local").limit(1)
    )
    server = result.scalar_one_or_none()

    if server is None:
        server = WorkspaceServer(
            name="platform",
            hostname="localhost",
            server_type="local",
            port=0,
            username="root",
            workspace_root="/workspaces",
            status="online",
            max_concurrent_tasks=2,
        )
        db.add(server)
        await db.flush()
        logger.info("Seeded local platform workspace server")

    # Always re-discover agents on startup so the list stays current
    await _discover_platform_agents(db, server)


async def _discover_platform_agents(db: AsyncSession, server: WorkspaceServer) -> None:
    """Scan the local platform for installed agents and update the DB."""
    lcs = LocalCommandService()
    discovery = AgentDiscoveryService(lcs)

    try:
        agents = await discovery.discover_all()
    except Exception:
        logger.warning("Failed to discover agents on platform server", exc_info=True)
        return

    if not agents:
        return

    # Upsert discovered agents for the "admin" context
    for info in agents:
        existing = await db.execute(
            select(DiscoveredAgent).where(
                DiscoveredAgent.workspace_server_id == server.id,
                DiscoveredAgent.agent_name == info.agent_name,
                DiscoveredAgent.user_context == "admin",
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.path = info.path
            row.version = info.version
            row.available = info.available
            row.agent_type = info.agent_type
        else:
            db.add(
                DiscoveredAgent(
                    workspace_server_id=server.id,
                    agent_name=info.agent_name,
                    user_context="admin",
                    agent_type=info.agent_type,
                    path=info.path,
                    version=info.version,
                    available=info.available,
                )
            )

    await db.commit()
    logger.info("Discovered %d agents on platform server", len(agents))
