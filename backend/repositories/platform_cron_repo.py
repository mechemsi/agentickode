# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for PlatformCron CRUD."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.platform_crons import PlatformCron


class PlatformCronRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_all(self) -> list[PlatformCron]:
        result = await self._db.execute(
            select(PlatformCron).order_by(PlatformCron.enabled.desc(), PlatformCron.name)
        )
        return list(result.scalars().all())

    async def list_due(self) -> list[PlatformCron]:
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(PlatformCron).where(
                PlatformCron.enabled.is_(True),
                PlatformCron.next_run_at.isnot(None),
                PlatformCron.next_run_at <= now,
            )
        )
        return list(result.scalars().all())

    async def get_by_id(self, cron_id: int) -> PlatformCron | None:
        return await self._db.get(PlatformCron, cron_id)

    async def create(self, cron: PlatformCron) -> PlatformCron:
        self._db.add(cron)
        return cron

    async def delete(self, cron: PlatformCron) -> None:
        await self._db.delete(cron)
