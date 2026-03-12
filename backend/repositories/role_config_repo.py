# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for RoleConfig database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import RoleConfig


class RoleConfigRepository:
    """Encapsulates all RoleConfig database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[RoleConfig]:
        result = await self._session.execute(select(RoleConfig).order_by(RoleConfig.agent_name))
        return list(result.scalars().all())

    async def get_by_name(self, agent_name: str) -> RoleConfig | None:
        result = await self._session.execute(
            select(RoleConfig).where(RoleConfig.agent_name == agent_name)
        )
        return result.scalar_one_or_none()

    async def get_by_phase(self, phase_name: str) -> RoleConfig | None:
        result = await self._session.execute(
            select(RoleConfig).where(RoleConfig.phase_binding == phase_name)
        )
        return result.scalar_one_or_none()

    async def get_valid_role_names(self) -> set[str]:
        result = await self._session.execute(select(RoleConfig.agent_name))
        return set(result.scalars().all())

    async def create(self, config: RoleConfig) -> RoleConfig:
        self._session.add(config)
        await self._session.commit()
        await self._session.refresh(config)
        return config

    async def update(self, config: RoleConfig, data: dict) -> RoleConfig:
        for field, value in data.items():
            setattr(config, field, value)
        await self._session.commit()
        await self._session.refresh(config)
        return config

    async def delete(self, config: RoleConfig) -> None:
        await self._session.delete(config)
        await self._session.commit()