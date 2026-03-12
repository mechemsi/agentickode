# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for AppSetting database operations."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AppSetting


class AppSettingRepository:
    """Encapsulates all AppSetting database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, key: str) -> Any | None:
        """Get a setting value by key, returns None if not found."""
        row = await self._session.get(AppSetting, key)
        return row.value if row else None

    async def set(self, key: str, value: Any) -> AppSetting:
        """Upsert a setting value."""
        row = await self._session.get(AppSetting, key)
        if row:
            row.value = value
            row.updated_at = datetime.now(UTC)
        else:
            row = AppSetting(key=key, value=value)
            self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def get_all(self) -> dict[str, Any]:
        """Return all settings as a dict."""
        result = await self._session.execute(select(AppSetting))
        return {str(row.key): row.value for row in result.scalars().all()}