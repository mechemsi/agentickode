# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Import configuration data from an export envelope."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from backend.services.backup.entity_registry import (
    DEPENDENCY_ORDER,
    ENTITY_CONFIGS,
    EntityConfig,
)
from backend.services.backup.schema_version import validate_schema_version
from backend.services.backup.secret_handler import SecretHandler, SecretMode
from backend.services.backup.serializers import NameMaps, deserialize_entity


class ImportService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def preview(
        self,
        data: dict,
        entity_types: list[str] | None = None,
        password: str | None = None,
    ) -> dict:
        """Dry-run: return what *would* happen for each entity."""
        inner = data["autodev_export"]
        validate_schema_version(inner["schema_version"])

        secret_mode = inner.get("secret_mode", "plaintext")
        handler = self._make_handler(secret_mode, password, inner)

        types = entity_types or list(DEPENDENCY_ORDER)
        name_maps = await self._build_name_maps()
        results: dict[str, list[dict]] = {}

        for etype in DEPENDENCY_ORDER:
            if etype not in types:
                continue
            cfg = ENTITY_CONFIGS[etype]
            items = inner.get("entities", {}).get(cfg.export_key, [])
            entity_results: list[dict] = []
            for item in items:
                obj, _ = deserialize_entity(item, cfg, handler, name_maps)
                match_values = self._extract_match_values(item, cfg)
                existing = await self._find_existing(cfg, match_values)
                action = "update" if existing else "create"
                entity_results.append(
                    {
                        "match_key": match_values,
                        "action": action,
                    }
                )
            results[cfg.export_key] = entity_results
        return {"entities": results}

    async def execute(
        self,
        data: dict,
        entity_types: list[str] | None = None,
        conflict_resolution: str = "skip",
        password: str | None = None,
    ) -> dict:
        """Actually import entities, respecting dependency order."""
        inner = data["autodev_export"]
        validate_schema_version(inner["schema_version"])

        secret_mode = inner.get("secret_mode", "plaintext")
        handler = self._make_handler(secret_mode, password, inner)

        types = entity_types or list(DEPENDENCY_ORDER)
        name_maps = await self._build_name_maps()
        results: dict[str, dict] = {}

        for etype in DEPENDENCY_ORDER:
            if etype not in types:
                continue
            cfg = ENTITY_CONFIGS[etype]
            items = inner.get("entities", {}).get(cfg.export_key, [])
            created = 0
            updated = 0
            skipped = 0

            for item in items:
                obj, children = deserialize_entity(item, cfg, handler, name_maps)
                match_values = self._extract_match_values(item, cfg)
                existing = await self._find_existing(cfg, match_values)

                if existing:
                    if conflict_resolution == "skip":
                        skipped += 1
                        continue
                    elif conflict_resolution == "overwrite":
                        self._apply_update(existing, obj, cfg)
                        # Handle children (delete old, add new)
                        if cfg.children:
                            await self._replace_children(existing, children, cfg)
                        updated += 1
                    else:
                        skipped += 1
                        continue
                else:
                    self._session.add(obj)
                    await self._session.flush()
                    # Attach children with parent FK
                    if children:
                        pk = self._get_pk_value(obj, cfg)
                        for child in children:
                            child_cfg = cfg.children[0]
                            fk_col = self._get_child_fk_col(child_cfg)
                            setattr(child, fk_col, pk)
                            self._session.add(child)
                    created += 1

                # Rebuild name maps after insert (for later FK resolution)
                await self._session.flush()
                name_maps = await self._build_name_maps()

            results[cfg.export_key] = {
                "created": created,
                "updated": updated,
                "skipped": skipped,
            }

        await self._session.commit()
        return {"entities": results}

    # --- helpers ---

    @staticmethod
    def _make_handler(
        secret_mode: str,
        password: str | None,
        inner: dict,
    ) -> SecretHandler | None:
        if secret_mode == SecretMode.encrypted.value:
            salt = inner.get("encryption_salt", "")
            if not password:
                raise ValueError("Password required for encrypted backup")
            return SecretHandler.for_decrypt(password, salt)
        if secret_mode == SecretMode.plaintext.value:
            return SecretHandler(SecretMode.plaintext)
        return None  # redacted — leave as-is

    def _extract_match_values(self, item: dict, cfg: EntityConfig) -> dict:
        """Extract the fields used to match against existing rows."""
        return {f: item.get(f) for f in cfg.match_fields}

    async def _find_existing(self, cfg: EntityConfig, match_values: dict):
        """Query DB for an existing row matching the match fields."""
        stmt = select(cfg.model)
        for field_name, value in match_values.items():
            col = getattr(cfg.model, field_name, None)
            if col is not None:
                stmt = stmt.where(col == value)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _apply_update(existing, new_obj, cfg: EntityConfig) -> None:
        """Copy non-excluded, non-PK attributes from new_obj to existing."""
        mapper = sa_inspect(type(new_obj))
        pk_cols = {col.key for col in mapper.mapper.primary_key}
        for col in mapper.columns:
            if col.key in cfg.excluded_fields or col.key in pk_cols:
                continue
            value = getattr(new_obj, col.key)
            if value is not None:
                setattr(existing, col.key, value)

    async def _replace_children(self, parent, new_children, cfg: EntityConfig) -> None:
        """Delete existing children and add new ones."""
        child_cfg = cfg.children[0]
        fk_col = self._get_child_fk_col(child_cfg)
        pk = self._get_pk_value(parent, cfg)

        # Delete old children
        from sqlalchemy import delete

        await self._session.execute(
            delete(child_cfg.model).where(getattr(child_cfg.model, fk_col) == pk)
        )
        # Add new
        for child in new_children:
            setattr(child, fk_col, pk)
            self._session.add(child)

    @staticmethod
    def _get_pk_value(obj, cfg: EntityConfig):
        mapper = sa_inspect(type(obj))
        pk_col = mapper.mapper.primary_key[0].key
        return getattr(obj, pk_col)

    @staticmethod
    def _get_child_fk_col(child_cfg) -> str:
        """Infer the FK column name on the child model."""
        mapper = sa_inspect(child_cfg.model)
        for col in mapper.columns:
            for _fk in col.foreign_keys:
                return col.key
        raise ValueError(f"No FK found on {child_cfg.model.__name__}")

    async def _build_name_maps(self) -> NameMaps:
        """Build {table_name: {name: id}} for FK resolution."""
        from backend.models import OllamaServer, WorkspaceServer

        maps: NameMaps = {}
        rows = (await self._session.execute(select(WorkspaceServer.name, WorkspaceServer.id))).all()
        maps["workspace_servers"] = {r[0]: r[1] for r in rows}

        rows = (await self._session.execute(select(OllamaServer.name, OllamaServer.id))).all()
        maps["ollama_servers"] = {r[0]: r[1] for r in rows}
        return maps