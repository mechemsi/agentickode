# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for ProjectConfig database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ProjectConfig


class ProjectConfigRepository:
    """Encapsulates all ProjectConfig database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[ProjectConfig]:
        result = await self._session.execute(
            select(ProjectConfig).order_by(ProjectConfig.project_slug)
        )
        return list(result.scalars().all())

    async def list_by_server(self, server_id: int) -> list[ProjectConfig]:
        result = await self._session.execute(
            select(ProjectConfig)
            .where(ProjectConfig.workspace_server_id == server_id)
            .order_by(ProjectConfig.project_slug)
        )
        return list(result.scalars().all())

    async def get_by_id(self, project_id: str) -> ProjectConfig | None:
        return await self._session.get(ProjectConfig, project_id)

    async def get_by_git_repo(
        self, git_provider: str, owner: str, name: str
    ) -> ProjectConfig | None:
        result = await self._session.execute(
            select(ProjectConfig).where(
                ProjectConfig.git_provider == git_provider,
                ProjectConfig.repo_owner == owner,
                ProjectConfig.repo_name == name,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_repo(self, owner: str, name: str) -> ProjectConfig | None:
        """Find a project by owner/name regardless of git provider."""
        result = await self._session.execute(
            select(ProjectConfig).where(
                ProjectConfig.repo_owner == owner,
                ProjectConfig.repo_name == name,
            )
        )
        return result.scalars().first()

    async def create(self, project: ProjectConfig) -> ProjectConfig:
        self._session.add(project)
        await self._session.commit()
        await self._session.refresh(project)
        return project

    async def update(self, project: ProjectConfig, data: dict) -> ProjectConfig:
        for field, value in data.items():
            setattr(project, field, value)
        await self._session.commit()
        await self._session.refresh(project)
        return project

    async def delete(self, project: ProjectConfig) -> None:
        await self._session.delete(project)
        await self._session.commit()
