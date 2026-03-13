# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for NotificationChannel database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import NotificationChannel


class NotificationChannelRepository:
    """Encapsulates all NotificationChannel database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[NotificationChannel]:
        result = await self._session.execute(
            select(NotificationChannel).order_by(NotificationChannel.name)
        )
        return list(result.scalars().all())

    async def list_enabled(self) -> list[NotificationChannel]:
        result = await self._session.execute(
            select(NotificationChannel)
            .where(NotificationChannel.enabled.is_(True))
            .order_by(NotificationChannel.name)
        )
        return list(result.scalars().all())

    async def get(self, channel_id: int) -> NotificationChannel | None:
        return await self._session.get(NotificationChannel, channel_id)

    async def create(self, channel: NotificationChannel) -> NotificationChannel:
        self._session.add(channel)
        await self._session.commit()
        await self._session.refresh(channel)
        return channel

    async def update(self, channel: NotificationChannel, data: dict) -> NotificationChannel:
        for field, value in data.items():
            setattr(channel, field, value)
        await self._session.commit()
        await self._session.refresh(channel)
        return channel

    async def delete(self, channel: NotificationChannel) -> None:
        await self._session.delete(channel)
        await self._session.commit()
