# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for RoleAssignment database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.models import RoleAssignment


class RoleAssignmentRepository:
    """Encapsulates all RoleAssignment database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self, workspace_server_id: int | None = None) -> list[RoleAssignment]:
        stmt = (
            select(RoleAssignment)
            .options(
                joinedload(RoleAssignment.ollama_server),
                joinedload(RoleAssignment.workspace_server),
            )
            .order_by(RoleAssignment.role, RoleAssignment.priority)
        )
        if workspace_server_id is not None:
            stmt = stmt.where(RoleAssignment.workspace_server_id == workspace_server_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def list_for_scope(
        self, role: str, workspace_server_id: int | None
    ) -> list[RoleAssignment]:
        stmt = (
            select(RoleAssignment)
            .options(
                joinedload(RoleAssignment.ollama_server),
                joinedload(RoleAssignment.workspace_server),
            )
            .where(RoleAssignment.role == role)
            .where(RoleAssignment.workspace_server_id == workspace_server_id)
            .order_by(RoleAssignment.priority)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def upsert(self, data: dict) -> RoleAssignment:
        stmt = select(RoleAssignment).where(
            RoleAssignment.role == data["role"],
            RoleAssignment.workspace_server_id == data.get("workspace_server_id"),
            RoleAssignment.priority == data.get("priority", 0),
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.provider_type = data["provider_type"]
            existing.ollama_server_id = data.get("ollama_server_id")
            existing.model_name = data.get("model_name")
            existing.agent_name = data.get("agent_name")
        else:
            existing = RoleAssignment(
                role=data["role"],
                provider_type=data["provider_type"],
                ollama_server_id=data.get("ollama_server_id"),
                model_name=data.get("model_name"),
                agent_name=data.get("agent_name"),
                workspace_server_id=data.get("workspace_server_id"),
                priority=data.get("priority", 0),
            )
            self._session.add(existing)
        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def bulk_upsert(self, assignments: list[dict]) -> list[RoleAssignment]:
        results = []
        for a in assignments:
            r = await self.upsert(a)
            results.append(r)
        return results

    async def delete(self, assignment_id: int) -> None:
        stmt = select(RoleAssignment).where(RoleAssignment.id == assignment_id)
        result = await self._session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj:
            await self._session.delete(obj)
            await self._session.commit()