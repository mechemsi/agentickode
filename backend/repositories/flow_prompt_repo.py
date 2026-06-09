# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for FlowPrompt database operations (ADR-009)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import FlowPrompt


class FlowPromptRepository:
    """Encapsulates all FlowPrompt database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[FlowPrompt]:
        result = await self._session.execute(select(FlowPrompt).order_by(FlowPrompt.name))
        return list(result.scalars().all())

    async def get_by_id(self, flow_id: int) -> FlowPrompt | None:
        return await self._session.get(FlowPrompt, flow_id)

    async def get_by_name(self, name: str) -> FlowPrompt | None:
        result = await self._session.execute(select(FlowPrompt).where(FlowPrompt.name == name))
        return result.scalar_one_or_none()

    async def get_by_flow_type(self, flow_type: str) -> FlowPrompt | None:
        """First enabled flow prompt of a given type (used to resolve e.g. pr_review)."""
        result = await self._session.execute(
            select(FlowPrompt)
            .where(FlowPrompt.flow_type == flow_type, FlowPrompt.enabled.is_(True))
            .order_by(FlowPrompt.id)
        )
        return result.scalars().first()

    async def create(self, flow: FlowPrompt) -> FlowPrompt:
        self._session.add(flow)
        await self._session.flush()
        return flow
