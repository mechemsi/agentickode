# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for WorkspaceReadiness database operations."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.readiness import WorkspaceReadiness


class WorkspaceReadinessRepository:
    """Encapsulates all WorkspaceReadiness database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, project_id: str, server_id: int) -> WorkspaceReadiness | None:
        result = await self._session.execute(
            select(WorkspaceReadiness).where(
                WorkspaceReadiness.project_id == project_id,
                WorkspaceReadiness.workspace_server_id == server_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_server(self, server_id: int) -> list[WorkspaceReadiness]:
        result = await self._session.execute(
            select(WorkspaceReadiness)
            .where(WorkspaceReadiness.workspace_server_id == server_id)
            .order_by(WorkspaceReadiness.project_id)
        )
        return list(result.scalars().all())

    async def is_valid(self, project_id: str, server_id: int) -> bool:
        """Return True when readiness exists, passed, and has not expired."""
        row = await self.get(project_id, server_id)
        if row is None or row.validation_status != "passed":
            return False
        if row.expires_at is None:
            return False
        return bool(row.expires_at > datetime.now(UTC))

    async def upsert(self, project_id: str, server_id: int, data: dict) -> WorkspaceReadiness:
        """Insert or update readiness for a (project, server) pair."""
        row = await self.get(project_id, server_id)
        if row is None:
            row = WorkspaceReadiness(project_id=project_id, workspace_server_id=server_id)
            self._session.add(row)
        for field, value in data.items():
            setattr(row, field, value)
        await self._session.commit()
        await self._session.refresh(row)
        return row
