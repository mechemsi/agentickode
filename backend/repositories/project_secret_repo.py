# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for ProjectSecret with encryption."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.instructions import ProjectSecret
from backend.services.encryption import decrypt_value, encrypt_value


class ProjectSecretRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_for_project(self, project_id: str) -> list[ProjectSecret]:
        result = await self._session.execute(
            select(ProjectSecret).where(ProjectSecret.project_id == project_id)
        )
        return list(result.scalars().all())

    async def get_by_id(self, secret_id: int) -> ProjectSecret | None:
        return await self._session.get(ProjectSecret, secret_id)

    async def create(
        self,
        project_id: str,
        name: str,
        value: str,
        inject_as: str = "env_var",
        phase_scope: str | None = None,
    ) -> ProjectSecret:
        secret = ProjectSecret(
            project_id=project_id,
            name=name,
            encrypted_value=encrypt_value(value),
            inject_as=inject_as,
            phase_scope=phase_scope,
        )
        self._session.add(secret)
        await self._session.commit()
        await self._session.refresh(secret)
        return secret

    async def update(self, secret: ProjectSecret, data: dict) -> ProjectSecret:
        if "value" in data:
            secret.encrypted_value = encrypt_value(data.pop("value"))
        for key, val in data.items():
            if hasattr(secret, key):
                setattr(secret, key, val)
        await self._session.commit()
        await self._session.refresh(secret)
        return secret

    async def delete(self, secret: ProjectSecret) -> None:
        await self._session.delete(secret)
        await self._session.commit()

    async def get_decrypted_for_phase(
        self, project_id: str, phase_name: str
    ) -> tuple[dict[str, str], list[tuple[str, str]]]:
        """Return (env_vars_dict, prompt_secrets_list) for a given phase."""
        secrets = await self.list_for_project(project_id)
        env_vars: dict[str, str] = {}
        prompt_secrets: list[tuple[str, str]] = []

        for s in secrets:
            if s.phase_scope:
                phases = [p.strip() for p in s.phase_scope.split(",")]
                if phase_name not in phases:
                    continue
            decrypted = decrypt_value(s.encrypted_value)
            if s.inject_as == "env_var":
                env_vars[s.name] = decrypted
            else:
                prompt_secrets.append((s.name, decrypted))

        return env_vars, prompt_secrets