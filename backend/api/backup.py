# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Backup export / import API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.backup import (
    ExportRequest,
    ImportOptions,
)
from backend.services.backup.export_service import ExportService
from backend.services.backup.import_service import ImportService
from backend.services.backup.secret_handler import SecretMode as HandlerSecretMode

router = APIRouter(prefix="/backup", tags=["backup"])


@router.post("/export")
async def export_config(
    req: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = ExportService(db)
    handler_mode = HandlerSecretMode(req.secret_mode.value)

    if req.project_id:
        envelope = await svc.export_project(
            project_id=req.project_id,
            secret_mode=handler_mode,
            password=req.encryption_password,
        )
    else:
        envelope = await svc.export_config(
            entity_types=req.entity_types,
            secret_mode=handler_mode,
            password=req.encryption_password,
        )

    return JSONResponse(
        content=envelope,
        headers={
            "Content-Disposition": "attachment; filename=autodev-backup.json",
        },
    )


@router.post("/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    options: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
):
    opts = ImportOptions(**json.loads(options))
    content = await file.read()
    data = json.loads(content)

    svc = ImportService(db)
    result = await svc.preview(
        data=data,
        entity_types=opts.entity_types,
        password=opts.encryption_password,
    )
    return result


@router.post("/import")
async def import_config(
    file: UploadFile = File(...),
    options: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
):
    opts = ImportOptions(**json.loads(options))
    content = await file.read()
    data = json.loads(content)

    svc = ImportService(db)
    result = await svc.execute(
        data=data,
        entity_types=opts.entity_types,
        conflict_resolution=opts.conflict_resolution.value,
        password=opts.encryption_password,
    )
    return result