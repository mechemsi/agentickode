# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Serialize SQLAlchemy models to/from export dicts with FK name resolution."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from backend.services.backup.entity_registry import EntityConfig, FKMapping
from backend.services.backup.secret_handler import SecretHandler

# Type alias: { "workspace_servers": { "coding-01": 3 }, ... }
NameMaps = dict[str, dict[str, int]]


async def build_name_maps(
    session: AsyncSession,
    fk_mappings: list[FKMapping],
) -> NameMaps:
    """Query DB to build ``{entity_key: {name: id}}`` lookups for FK re-mapping."""
    maps: NameMaps = {}
    seen: set[str] = set()
    for fk in fk_mappings:
        table = fk.target_model.__tablename__
        if table in seen:
            continue
        seen.add(table)
        pk_col = sa_inspect(fk.target_model).mapper.primary_key[0].name
        name_col = getattr(fk.target_model, fk.target_name_col)
        pk = getattr(fk.target_model, pk_col)
        rows = (await session.execute(select(name_col, pk))).all()
        maps[table] = {str(row[0]): row[1] for row in rows}
    return maps


def _get_column_value(obj: object, col_name: str):
    """Get attribute value, handling the metadata_ → 'metadata' alias."""
    return getattr(obj, col_name)


def serialize_entity(
    obj: object,
    cfg: EntityConfig,
    secret_handler: SecretHandler,
    id_to_name: dict[str, dict[int, str]] | None = None,
) -> dict:
    """Convert a single ORM object to an export dict.

    - Strips excluded fields
    - Resolves integer FK IDs to human-readable names
    - Encrypts/redacts secret fields
    - Nests children
    """
    mapper = sa_inspect(type(obj))
    data: dict = {}
    secret_cols = {sf.column for sf in cfg.secret_fields}
    fk_cols = {fk.column for fk in cfg.fk_mappings}

    for col in mapper.columns:  # type: ignore[union-attr]
        col_name = col.key
        if col_name in cfg.excluded_fields:
            continue
        if col_name in fk_cols:
            continue  # replaced by export_field below
        value = _get_column_value(obj, col_name)
        if col_name in secret_cols:
            sf = next(s for s in cfg.secret_fields if s.column == col_name)
            if sf.is_dict:
                value = secret_handler.process_dict_values(value)
            else:
                value = secret_handler.process_text(value)
        data[col_name] = value

    # Resolve FK IDs → names
    if id_to_name:
        for fk in cfg.fk_mappings:
            fk_value = _get_column_value(obj, fk.column)
            resolved: str | None = None
            if fk_value is not None:
                table = fk.target_model.__tablename__
                resolved = id_to_name.get(table, {}).get(fk_value)
            data[fk.export_field] = resolved

    # Nest children
    for child_cfg in cfg.children:
        children = getattr(obj, child_cfg.relationship_attr, [])
        child_mapper = sa_inspect(child_cfg.model)
        child_list: list[dict] = []
        for child in children:
            child_data: dict = {}
            for col in child_mapper.columns:
                if col.key in child_cfg.excluded_fields:
                    continue
                child_data[col.key] = _get_column_value(child, col.key)
            child_list.append(child_data)
        data["prompt_overrides"] = child_list

    return data


def deserialize_entity(
    data: dict,
    cfg: EntityConfig,
    secret_handler: SecretHandler | None,
    name_maps: NameMaps | None = None,
) -> tuple[object, list[object]]:
    """Convert an export dict back to an ORM object (+ child objects).

    - Resolves name-based FKs back to integer IDs
    - Decrypts secret fields
    Returns (parent_obj, [child_objs]).
    """
    kwargs: dict = {}
    secret_map = {sf.column: sf for sf in cfg.secret_fields}
    fk_export_map = {fk.export_field: fk for fk in cfg.fk_mappings}

    mapper = sa_inspect(cfg.model)
    column_names = {col.key for col in mapper.columns}

    for key, value in data.items():
        # Skip child arrays and FK export fields handled below
        if key in ("prompt_overrides",):
            continue
        if key in fk_export_map:
            fk = fk_export_map[key]
            if value is not None and name_maps:
                table = fk.target_model.__tablename__
                resolved_id = name_maps.get(table, {}).get(str(value))
                kwargs[fk.column] = resolved_id
            else:
                kwargs[fk.column] = None
            continue
        if key not in column_names:
            continue

        # Decrypt secrets
        if key in secret_map and secret_handler:
            sf = secret_map[key]
            if sf.is_dict:
                value = secret_handler.decrypt_dict_values(value)
            else:
                value = secret_handler.decrypt_text(value)

        kwargs[key] = value

    parent = cfg.model(**kwargs)

    # Deserialize children
    children: list[object] = []
    for child_cfg in cfg.children:
        child_data_list = data.get("prompt_overrides", [])
        for child_data in child_data_list:
            child_kwargs = {
                k: v for k, v in child_data.items() if k not in child_cfg.excluded_fields
            }
            children.append(child_cfg.model(**child_kwargs))

    return parent, children
