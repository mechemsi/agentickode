# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pydantic schemas for the backup export-import feature."""

from __future__ import annotations

import enum

from pydantic import BaseModel


class SecretMode(str, enum.Enum):
    plaintext = "plaintext"
    redacted = "redacted"
    encrypted = "encrypted"


class ConflictResolution(str, enum.Enum):
    skip = "skip"
    overwrite = "overwrite"


class ExportRequest(BaseModel):
    entity_types: list[str] | None = None
    secret_mode: SecretMode = SecretMode.redacted
    encryption_password: str | None = None
    project_id: str | None = None


class ImportOptions(BaseModel):
    entity_types: list[str] | None = None
    conflict_resolution: ConflictResolution = ConflictResolution.skip
    encryption_password: str | None = None


class PreviewItemAction(BaseModel):
    match_key: dict
    action: str  # "create" | "update"


class PreviewEntityResult(BaseModel):
    entity_type: str
    items: list[PreviewItemAction]


class PreviewResult(BaseModel):
    entities: dict[str, list[PreviewItemAction]]


class ImportEntityResult(BaseModel):
    created: int
    updated: int
    skipped: int


class ImportResult(BaseModel):
    entities: dict[str, ImportEntityResult]