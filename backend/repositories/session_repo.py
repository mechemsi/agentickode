# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for CliSession database operations."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sessions import CliSession


class CliSessionRepository:
    """Encapsulates all CliSession database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, cli_session: CliSession) -> CliSession:
        self._session.add(cli_session)
        await self._session.flush()
        return cli_session

    async def get_by_id(self, session_id: int) -> CliSession | None:
        return await self._session.get(CliSession, session_id)

    async def get_by_session_id(self, session_id: str) -> CliSession | None:
        result = await self._session.execute(
            select(CliSession).where(CliSession.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_active(
        self, server_id: int | None = None, project_id: str | None = None
    ) -> list[CliSession]:
        stmt = select(CliSession).where(
            CliSession.status.in_(["starting", "active", "idle", "detached"])
        )
        if server_id:
            stmt = stmt.where(CliSession.workspace_server_id == server_id)
        if project_id:
            stmt = stmt.where(CliSession.project_id == project_id)
        stmt = stmt.order_by(CliSession.last_activity_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_server(
        self, server_id: int, include_closed: bool = False
    ) -> list[CliSession]:
        stmt = select(CliSession).where(CliSession.workspace_server_id == server_id)
        if not include_closed:
            stmt = stmt.where(CliSession.status.notin_(["closed"]))
        stmt = stmt.order_by(CliSession.last_activity_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_active_by_server(self, server_id: int) -> int:
        result = await self._session.execute(
            select(func.count(CliSession.id)).where(
                CliSession.workspace_server_id == server_id,
                CliSession.status.in_(["starting", "active", "idle", "detached"]),
            )
        )
        return result.scalar() or 0

    async def get_by_task_run(self, task_run_id: int) -> CliSession | None:
        result = await self._session.execute(
            select(CliSession).where(
                CliSession.task_run_id == task_run_id,
                CliSession.status.notin_(["closed"]),
            )
        )
        return result.scalar_one_or_none()
