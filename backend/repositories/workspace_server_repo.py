# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for WorkspaceServer database operations."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import DiscoveredAgent, ProjectConfig, WorkspaceServer


class WorkspaceServerRepository:
    """Encapsulates all WorkspaceServer database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[WorkspaceServer]:
        result = await self._session.execute(select(WorkspaceServer).order_by(WorkspaceServer.name))
        return list(result.scalars().all())

    async def get_by_id(self, server_id: int) -> WorkspaceServer | None:
        return await self._session.get(WorkspaceServer, server_id)

    async def get_by_id_with_agents(self, server_id: int) -> WorkspaceServer | None:
        result = await self._session.execute(
            select(WorkspaceServer)
            .where(WorkspaceServer.id == server_id)
            .options(selectinload(WorkspaceServer.agents))
        )
        return result.scalar_one_or_none()

    async def get_by_hostname(self, hostname: str) -> WorkspaceServer | None:
        result = await self._session.execute(
            select(WorkspaceServer).where(WorkspaceServer.hostname == hostname)
        )
        return result.scalar_one_or_none()

    async def create(self, server: WorkspaceServer) -> WorkspaceServer:
        self._session.add(server)
        await self._session.commit()
        await self._session.refresh(server)
        return server

    async def update(self, server: WorkspaceServer, data: dict) -> WorkspaceServer:
        for field, value in data.items():
            setattr(server, field, value)
        await self._session.commit()
        await self._session.refresh(server)
        return server

    async def delete(self, server: WorkspaceServer) -> None:
        # Nullify project FK references before deleting
        await self._session.execute(
            select(ProjectConfig).where(ProjectConfig.workspace_server_id == server.id)
        )
        for proj in (
            (
                await self._session.execute(
                    select(ProjectConfig).where(ProjectConfig.workspace_server_id == server.id)
                )
            )
            .scalars()
            .all()
        ):
            proj.workspace_server_id = None

        await self._session.delete(server)
        await self._session.commit()

    async def get_agent_count(self, server_id: int) -> int:
        """Count worker-context agents for a server."""
        result = await self._session.execute(
            select(func.count(DiscoveredAgent.id)).where(
                DiscoveredAgent.workspace_server_id == server_id,
                DiscoveredAgent.user_context == "worker",
            )
        )
        return result.scalar_one()

    async def get_project_count(self, server_id: int) -> int:
        result = await self._session.execute(
            select(func.count(ProjectConfig.project_id)).where(
                ProjectConfig.workspace_server_id == server_id
            )
        )
        return result.scalar_one()

    async def replace_agents(self, server_id: int, agents: list[DiscoveredAgent]) -> None:
        """Delete all existing agents and insert new ones."""
        existing = await self._session.execute(
            select(DiscoveredAgent).where(DiscoveredAgent.workspace_server_id == server_id)
        )
        for agent in existing.scalars().all():
            await self._session.delete(agent)
        await self._session.flush()
        for agent in agents:
            agent.workspace_server_id = server_id
            self._session.add(agent)
        await self._session.commit()

    async def replace_agents_for_context(
        self, server_id: int, user_context: str, agents: list[DiscoveredAgent]
    ) -> None:
        """Delete agents with matching user_context and insert new ones."""
        existing = await self._session.execute(
            select(DiscoveredAgent).where(
                DiscoveredAgent.workspace_server_id == server_id,
                DiscoveredAgent.user_context == user_context,
            )
        )
        for agent in existing.scalars().all():
            await self._session.delete(agent)
        await self._session.flush()
        for agent in agents:
            agent.workspace_server_id = server_id
            agent.user_context = user_context
            self._session.add(agent)
        await self._session.commit()
