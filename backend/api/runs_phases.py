# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent-invocation (cost/telemetry) endpoints for task runs."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas import AgentInvocationDetail, AgentInvocationOut

logger = logging.getLogger("agentickode.runs")
router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}/invocations", response_model=list[AgentInvocationOut])
async def list_run_invocations(
    run_id: int,
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    from backend.models import AgentInvocation

    stmt = select(AgentInvocation).where(AgentInvocation.run_id == run_id)
    if session_id:
        stmt = stmt.where(AgentInvocation.session_id == session_id)
    result = await db.execute(stmt.order_by(AgentInvocation.started_at))
    return result.scalars().all()


@router.get("/runs/{run_id}/invocations/{invocation_id}", response_model=AgentInvocationDetail)
async def get_invocation_detail(
    run_id: int, invocation_id: int, db: AsyncSession = Depends(get_db)
):
    from backend.models import AgentInvocation

    result = await db.execute(
        select(AgentInvocation).where(
            AgentInvocation.id == invocation_id, AgentInvocation.run_id == run_id
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Invocation not found")
    return inv
