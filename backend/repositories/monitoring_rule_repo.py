# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for MonitoringRule database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agents import MonitoringRule


class MonitoringRuleRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_by_project(self, project_id: str) -> list[MonitoringRule]:
        result = await self._session.execute(
            select(MonitoringRule)
            .where(MonitoringRule.project_id == project_id)
            .order_by(MonitoringRule.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_source(self, source: str) -> list[MonitoringRule]:
        result = await self._session.execute(
            select(MonitoringRule).where(
                MonitoringRule.source == source,
                MonitoringRule.enabled.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_by_id(self, rule_id: int) -> MonitoringRule | None:
        result = await self._session.execute(
            select(MonitoringRule).where(MonitoringRule.id == rule_id)
        )
        return result.scalar_one_or_none()

    async def create(self, rule: MonitoringRule) -> MonitoringRule:
        self._session.add(rule)
        await self._session.flush()
        await self._session.refresh(rule)
        return rule

    async def delete(self, rule: MonitoringRule) -> None:
        await self._session.delete(rule)
