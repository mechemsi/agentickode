# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for AutomationRule database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.automation_rules import AutomationRule


class AutomationRuleRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_enabled(self) -> list[AutomationRule]:
        result = await self._session.execute(
            select(AutomationRule).where(AutomationRule.enabled.is_(True))
        )
        return list(result.scalars().all())

    async def list_by_project(self, project_id: str) -> list[AutomationRule]:
        result = await self._session.execute(
            select(AutomationRule)
            .where(
                (AutomationRule.project_id == project_id) | (AutomationRule.project_id.is_(None))
            )
            .order_by(AutomationRule.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, rule_id: int) -> AutomationRule | None:
        result = await self._session.execute(
            select(AutomationRule).where(AutomationRule.id == rule_id)
        )
        return result.scalar_one_or_none()

    async def create(self, rule: AutomationRule) -> AutomationRule:
        self._session.add(rule)
        await self._session.flush()
        await self._session.refresh(rule)
        return rule

    async def delete(self, rule: AutomationRule) -> None:
        await self._session.delete(rule)
