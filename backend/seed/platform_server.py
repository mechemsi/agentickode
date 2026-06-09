# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Seed the built-in 'platform' workspace server (local execution)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import DiscoveredAgent, WorkspaceServer
from backend.services.workspace.agent_discovery import AgentDiscoveryService
from backend.services.workspace.command_executor import executor_for_server

logger = logging.getLogger("agentickode.seed")


async def seed_platform_server(db: AsyncSession) -> None:
    """Ensure the platform workspace server exists and agents are discovered.

    By default this is a ``local`` server that executes inside the backend
    container. When ``PLATFORM_SSH_HOST`` is set it is instead seeded/updated as
    a ``remote`` SSH target (the real host) — opt-in, see the host-execution
    runbook. ``PLATFORM_USER`` sets the run-as user (terminal/chat/agent run as
    that user via runuser); empty keeps the current root behaviour.
    """
    result = await db.execute(
        select(WorkspaceServer)
        .where(WorkspaceServer.server_type.in_(["local", "remote"]))
        .where(WorkspaceServer.name == "platform")
        .limit(1)
    )
    server = result.scalar_one_or_none()
    if server is None:
        # Fall back to any local server (pre-existing platform row without the name filter)
        result = await db.execute(
            select(WorkspaceServer).where(WorkspaceServer.server_type == "local").limit(1)
        )
        server = result.scalar_one_or_none()

    ssh_host = settings.platform_ssh_host.strip()
    run_as = settings.platform_user.strip() or None

    if server is None:
        if ssh_host:
            server = WorkspaceServer(
                name="platform",
                hostname=ssh_host,
                server_type="remote",
                port=settings.platform_ssh_port,
                username="root",
                worker_user=run_as,
                workspace_root=settings.platform_workspace_root or "/workspaces",
                status="online",
                max_concurrent_tasks=2,
            )
        else:
            server = WorkspaceServer(
                name="platform",
                hostname="localhost",
                server_type="local",
                port=0,
                username="root",
                worker_user=run_as,
                workspace_root="/workspaces",
                status="online",
                max_concurrent_tasks=2,
            )
        db.add(server)
        await db.flush()
        logger.info("Seeded platform workspace server (ssh_host=%r)", ssh_host or None)
    else:
        # Idempotent reconcile of the opt-in host-execution config.
        if ssh_host and server.server_type != "remote":
            server.server_type = "remote"
            server.hostname = ssh_host
            server.port = settings.platform_ssh_port
            if settings.platform_workspace_root:
                server.workspace_root = settings.platform_workspace_root
            logger.info("Platform server switched to SSH-to-host (%s)", ssh_host)
        # Set the run-as user when configured and not already set.
        if run_as and not server.worker_user:
            server.worker_user = run_as
        await db.flush()

    # Always re-discover agents on startup so the list stays current
    await _discover_platform_agents(db, server)


async def _discover_platform_agents(db: AsyncSession, server: WorkspaceServer) -> None:
    """Scan the platform for installed agents and update the DB."""
    discovery = AgentDiscoveryService(executor_for_server(server))

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
