# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for ProjectInstruction and ProjectInstructionVersion."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.instructions import ProjectInstruction, ProjectInstructionVersion


class ProjectInstructionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_for_project(self, project_id: str) -> list[ProjectInstruction]:
        result = await self._session.execute(
            select(ProjectInstruction).where(ProjectInstruction.project_id == project_id)
        )
        return list(result.scalars().all())

    async def get_global(self, project_id: str) -> ProjectInstruction | None:
        return await self._get_by_phase(project_id, "__global__")

    async def get_for_phase(self, project_id: str, phase_name: str) -> ProjectInstruction | None:
        return await self._get_by_phase(project_id, phase_name)

    async def _get_by_phase(self, project_id: str, phase_name: str) -> ProjectInstruction | None:
        result = await self._session.execute(
            select(ProjectInstruction).where(
                ProjectInstruction.project_id == project_id,
                ProjectInstruction.phase_name == phase_name,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, project_id: str, phase_name: str, content: str) -> ProjectInstruction:
        instruction = await self._get_by_phase(project_id, phase_name)
        if instruction:
            instruction.content = content
        else:
            instruction = ProjectInstruction(
                project_id=project_id, phase_name=phase_name, content=content
            )
            self._session.add(instruction)
        await self._session.flush()
        # Create version snapshot
        version = ProjectInstructionVersion(instruction_id=instruction.id, content=content)
        self._session.add(version)
        await self._session.commit()
        await self._session.refresh(instruction)
        return instruction

    async def delete(self, instruction: ProjectInstruction) -> None:
        await self._session.delete(instruction)
        await self._session.commit()

    async def get_versions(self, instruction_id: int) -> list[ProjectInstructionVersion]:
        result = await self._session.execute(
            select(ProjectInstructionVersion)
            .where(ProjectInstructionVersion.instruction_id == instruction_id)
            .order_by(ProjectInstructionVersion.changed_at.desc())
        )
        return list(result.scalars().all())
