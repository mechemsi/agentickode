# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Export configuration data to a portable envelope."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import ProjectConfig, WorkspaceServer
from backend.services.backup.entity_registry import (
    DEPENDENCY_ORDER,
    ENTITY_CONFIGS,
    EntityConfig,
)
from backend.services.backup.schema_version import CURRENT_SCHEMA_VERSION
from backend.services.backup.secret_handler import SecretHandler, SecretMode
from backend.services.backup.serializers import serialize_entity


class ExportService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def export_config(
        self,
        entity_types: list[str] | None = None,
        secret_mode: SecretMode = SecretMode.redacted,
        password: str | None = None,
    ) -> dict:
        """Export all (or selected) entity types to an envelope dict."""
        handler = SecretHandler(secret_mode, password)
        types = entity_types or list(DEPENDENCY_ORDER)
        id_to_name = await self._build_id_to_name_maps()

        entities: dict[str, list[dict]] = {}
        for etype in DEPENDENCY_ORDER:
            if etype not in types:
                continue
            cfg = ENTITY_CONFIGS[etype]
            rows = await self._load_entities(cfg)
            entities[cfg.export_key] = [
                serialize_entity(row, cfg, handler, id_to_name) for row in rows
            ]

        envelope: dict = {
            "agentickode_export": {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "exported_at": datetime.now(UTC).isoformat(),
                "secret_mode": secret_mode.value,
                "entities": entities,
            }
        }
        if handler.salt_b64:
            envelope["agentickode_export"]["encryption_salt"] = handler.salt_b64
        return envelope

    async def export_project(
        self,
        project_id: str,
        secret_mode: SecretMode = SecretMode.redacted,
        password: str | None = None,
    ) -> dict:
        """Export a single project + its dependency objects."""
        handler = SecretHandler(secret_mode, password)
        id_to_name = await self._build_id_to_name_maps()

        proj = (
            await self._session.execute(
                select(ProjectConfig).where(ProjectConfig.project_id == project_id)
            )
        ).scalar_one_or_none()
        if proj is None:
            raise ValueError(f"Project '{project_id}' not found")

        entities: dict[str, list[dict]] = {}
        cfg = ENTITY_CONFIGS["project_configs"]
        entities["project_configs"] = [serialize_entity(proj, cfg, handler, id_to_name)]

        # Include the linked workspace server if present
        if proj.workspace_server_id:
            ws_cfg = ENTITY_CONFIGS["workspace_servers"]
            ws = (
                await self._session.execute(
                    select(WorkspaceServer).where(WorkspaceServer.id == proj.workspace_server_id)
                )
            ).scalar_one_or_none()
            if ws:
                entities["workspace_servers"] = [serialize_entity(ws, ws_cfg, handler, id_to_name)]

        envelope: dict = {
            "agentickode_export": {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "exported_at": datetime.now(UTC).isoformat(),
                "secret_mode": secret_mode.value,
                "entities": entities,
            }
        }
        if handler.salt_b64:
            envelope["agentickode_export"]["encryption_salt"] = handler.salt_b64
        return envelope

    # --- helpers ---

    async def _load_entities(self, cfg: EntityConfig) -> list:
        stmt = select(cfg.model)
        # Eager-load children
        for child in cfg.children:
            stmt = stmt.options(selectinload(getattr(cfg.model, child.relationship_attr)))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _build_id_to_name_maps(self) -> dict[str, dict[int, str]]:
        """Build {table_name: {id: name}} for FK resolution during export."""
        maps: dict[str, dict[int, str]] = {}
        # WorkspaceServer
        rows = (await self._session.execute(select(WorkspaceServer.id, WorkspaceServer.name))).all()
        maps["workspace_servers"] = {r[0]: r[1] for r in rows}
        # OllamaServer
        from backend.models import OllamaServer

        rows = (await self._session.execute(select(OllamaServer.id, OllamaServer.name))).all()
        maps["ollama_servers"] = {r[0]: r[1] for r in rows}
        return maps
