# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Analytics endpoints for run statistics and trends."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.analytics_repo import AnalyticsRepository
from backend.schemas import AnalyticsSummary

router = APIRouter(tags=["analytics"])


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    days: int = Query(default=14, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsSummary:
    repo = AnalyticsRepository(db)
    data = await repo.get_summary(days=days)
    return AnalyticsSummary(**data)
