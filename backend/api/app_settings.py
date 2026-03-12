# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""API endpoints for application settings."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.app_setting_repo import AppSettingRepository

router = APIRouter(tags=["settings"])


class AppSettingUpdate(BaseModel):
    value: Any


@router.get("/app-settings")
async def get_all_settings(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    repo = AppSettingRepository(db)
    return await repo.get_all()


@router.put("/app-settings/{key}")
async def update_setting(
    key: str,
    body: AppSettingUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repo = AppSettingRepository(db)
    setting = await repo.set(key, body.value)
    return {"key": setting.key, "value": setting.value}