# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for ProjectConfig database operations."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import ProjectConfig, ProjectWorkspaceServer


class ProjectConfigRepository:
    """Encapsulates all ProjectConfig database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[ProjectConfig]:
        result = await self._session.execute(
            select(ProjectConfig)
            .options(selectinload(ProjectConfig.workspace_servers))
            .order_by(ProjectConfig.project_slug)
        )
        return list(result.scalars().all())

    async def list_by_server(self, server_id: int) -> list[ProjectConfig]:
        result = await self._session.execute(
            select(ProjectConfig)
            .options(selectinload(ProjectConfig.workspace_servers))
            .join(
                ProjectWorkspaceServer,
                ProjectWorkspaceServer.project_id == ProjectConfig.project_id,
            )
            .where(ProjectWorkspaceServer.workspace_server_id == server_id)
            .order_by(ProjectConfig.project_slug)
        )
        return list(result.scalars().all())

    async def get_by_id(self, project_id: str) -> ProjectConfig | None:
        result = await self._session.execute(
            select(ProjectConfig)
            .options(selectinload(ProjectConfig.workspace_servers))
            .where(ProjectConfig.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_by_git_repo(
        self, git_provider: str, owner: str, name: str
    ) -> ProjectConfig | None:
        result = await self._session.execute(
            select(ProjectConfig)
            .options(selectinload(ProjectConfig.workspace_servers))
            .where(
                ProjectConfig.git_provider == git_provider,
                ProjectConfig.repo_owner == owner,
                ProjectConfig.repo_name == name,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_repo(self, owner: str, name: str) -> ProjectConfig | None:
        """Find a project by owner/name regardless of git provider."""
        result = await self._session.execute(
            select(ProjectConfig)
            .options(selectinload(ProjectConfig.workspace_servers))
            .where(
                ProjectConfig.repo_owner == owner,
                ProjectConfig.repo_name == name,
            )
        )
        return result.scalars().first()

    async def create(self, project: ProjectConfig, workspace_server_ids: list[int] | None = None) -> ProjectConfig:
        self._session.add(project)
        await self._session.flush()  # get project_id populated before inserting join rows
        if workspace_server_ids:
            for idx, server_id in enumerate(workspace_server_ids):
                row = ProjectWorkspaceServer(
                    project_id=project.project_id,
                    workspace_server_id=server_id,
                    priority=idx,
                )
                self._session.add(row)
        await self._session.commit()
        await self._session.refresh(project)
        # Eagerly load workspace_servers after commit
        result = await self._session.execute(
            select(ProjectConfig)
            .options(selectinload(ProjectConfig.workspace_servers))
            .where(ProjectConfig.project_id == project.project_id)
        )
        return result.scalar_one()

    async def update(self, project: ProjectConfig, data: dict) -> ProjectConfig:
        workspace_server_ids = data.pop("workspace_server_ids", None)
        for field, value in data.items():
            setattr(project, field, value)
        if workspace_server_ids is not None:
            await self._session.execute(
                delete(ProjectWorkspaceServer).where(
                    ProjectWorkspaceServer.project_id == project.project_id
                )
            )
            for idx, server_id in enumerate(workspace_server_ids):
                row = ProjectWorkspaceServer(
                    project_id=project.project_id,
                    workspace_server_id=server_id,
                    priority=idx,
                )
                self._session.add(row)
        await self._session.commit()
        # Eagerly reload with workspace_servers
        result = await self._session.execute(
            select(ProjectConfig)
            .options(selectinload(ProjectConfig.workspace_servers))
            .where(ProjectConfig.project_id == project.project_id)
        )
        return result.scalar_one()

    async def delete(self, project: ProjectConfig) -> None:
        await self._session.delete(project)
        await self._session.commit()
