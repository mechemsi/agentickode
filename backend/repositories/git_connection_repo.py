# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for GitConnection with encryption."""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.git_connections import GitConnection
from backend.schemas.git_connections import GitConnectionCreate
from backend.services.encryption import decrypt_value, encrypt_value


class GitConnectionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(
        self,
        scope: str | None = None,
        workspace_server_id: int | None = None,
        project_id: str | None = None,
    ) -> list[GitConnection]:
        stmt = select(GitConnection)
        if scope:
            stmt = stmt.where(GitConnection.scope == scope)
        if workspace_server_id is not None:
            stmt = stmt.where(GitConnection.workspace_server_id == workspace_server_id)
        if project_id is not None:
            stmt = stmt.where(GitConnection.project_id == project_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, connection_id: int) -> GitConnection | None:
        return await self._session.get(GitConnection, connection_id)

    async def create(self, data: GitConnectionCreate) -> GitConnection:
        conn = GitConnection(
            name=data.name,
            provider=data.provider,
            base_url=data.base_url,
            token_enc=encrypt_value(data.token),
            scope=data.scope,
            workspace_server_id=data.workspace_server_id,
            project_id=data.project_id,
            is_default=data.is_default,
        )
        self._session.add(conn)
        await self._session.commit()
        await self._session.refresh(conn)
        return conn

    async def update(self, conn: GitConnection, data: dict) -> GitConnection:
        if "token" in data:
            conn.token_enc = encrypt_value(data.pop("token"))
        for key, val in data.items():
            if hasattr(conn, key):
                setattr(conn, key, val)
        await self._session.commit()
        await self._session.refresh(conn)
        return conn

    async def delete(self, conn: GitConnection) -> None:
        await self._session.delete(conn)
        await self._session.commit()

    async def resolve_token(
        self,
        provider: str,
        workspace_server_id: int | None = None,
        project_id: str | None = None,
    ) -> str | None:
        """Resolve decrypted token following priority: project > server > global default."""
        if project_id:
            result = await self._session.execute(
                select(GitConnection).where(
                    and_(
                        GitConnection.provider == provider,
                        GitConnection.scope == "project",
                        GitConnection.project_id == project_id,
                    )
                )
            )
            conn = result.scalars().first()
            if conn:
                return decrypt_value(conn.token_enc)

        if workspace_server_id is not None:
            result = await self._session.execute(
                select(GitConnection).where(
                    and_(
                        GitConnection.provider == provider,
                        GitConnection.scope == "server",
                        GitConnection.workspace_server_id == workspace_server_id,
                    )
                )
            )
            conn = result.scalars().first()
            if conn:
                return decrypt_value(conn.token_enc)

        result = await self._session.execute(
            select(GitConnection).where(
                and_(
                    GitConnection.provider == provider,
                    GitConnection.scope == "global",
                    GitConnection.is_default.is_(True),
                )
            )
        )
        conn = result.scalars().first()
        if conn:
            return decrypt_value(conn.token_enc)

        return None

    async def list_for_server(self, workspace_server_id: int) -> list[GitConnection]:
        return await self.list_all(scope="server", workspace_server_id=workspace_server_id)

    async def list_for_project(self, project_id: str) -> list[GitConnection]:
        return await self.list_all(scope="project", project_id=project_id)
