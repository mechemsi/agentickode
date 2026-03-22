# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for ServerGroup database operations."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import ServerGroup, WorkspaceServer


class ServerGroupRepository:
    """Encapsulates all ServerGroup database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[ServerGroup]:
        result = await self._session.execute(select(ServerGroup).order_by(ServerGroup.name))
        return list(result.scalars().all())

    async def get_by_id(self, group_id: int) -> ServerGroup | None:
        return await self._session.get(ServerGroup, group_id)

    async def get_by_id_with_servers(self, group_id: int) -> ServerGroup | None:
        result = await self._session.execute(
            select(ServerGroup)
            .where(ServerGroup.id == group_id)
            .options(selectinload(ServerGroup.servers))
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> ServerGroup | None:
        result = await self._session.execute(select(ServerGroup).where(ServerGroup.name == name))
        return result.scalar_one_or_none()

    async def create(self, group: ServerGroup) -> ServerGroup:
        self._session.add(group)
        await self._session.commit()
        await self._session.refresh(group)
        return group

    async def update(self, group: ServerGroup, data: dict) -> ServerGroup:
        for field, value in data.items():
            setattr(group, field, value)
        await self._session.commit()
        await self._session.refresh(group)
        return group

    async def delete(self, group: ServerGroup) -> None:
        await self._session.delete(group)
        await self._session.commit()

    async def get_server_count(self, group_id: int) -> int:
        result = await self._session.execute(
            select(func.count(WorkspaceServer.id)).where(
                WorkspaceServer.server_group_id == group_id
            )
        )
        return result.scalar_one()
