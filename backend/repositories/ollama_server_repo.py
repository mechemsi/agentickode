# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for OllamaServer database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import OllamaServer


class OllamaServerRepository:
    """Encapsulates all OllamaServer database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[OllamaServer]:
        result = await self._session.execute(select(OllamaServer).order_by(OllamaServer.name))
        return list(result.scalars().all())

    async def get_by_id(self, server_id: int) -> OllamaServer | None:
        return await self._session.get(OllamaServer, server_id)

    async def create(self, server: OllamaServer) -> OllamaServer:
        self._session.add(server)
        await self._session.commit()
        await self._session.refresh(server)
        return server

    async def update(self, server: OllamaServer, data: dict) -> OllamaServer:
        for field, value in data.items():
            setattr(server, field, value)
        await self._session.commit()
        await self._session.refresh(server)
        return server

    async def delete(self, server: OllamaServer) -> None:
        await self._session.delete(server)
        await self._session.commit()
