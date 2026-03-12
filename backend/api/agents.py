# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent settings CRUD."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import AgentSettings, DiscoveredAgent
from backend.schemas import AgentSettingsIn, AgentSettingsOut

router = APIRouter(tags=["agents"])


@router.get("/agents", response_model=list[AgentSettingsOut])
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentSettings).order_by(AgentSettings.agent_name))
    return result.scalars().all()


@router.get("/agents/{name}", response_model=AgentSettingsOut)
async def get_agent(name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentSettings).where(AgentSettings.agent_name == name))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent '{name}' not found")
    return agent


@router.put("/agents/{name}", response_model=AgentSettingsOut)
async def update_agent(name: str, body: AgentSettingsIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentSettings).where(AgentSettings.agent_name == name))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent '{name}' not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(agent, field, value)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.get("/agents/{name}/availability")
async def get_agent_availability(name: str, db: AsyncSession = Depends(get_db)):
    """Get which workspace servers have this agent available."""
    result = await db.execute(
        select(DiscoveredAgent).where(
            DiscoveredAgent.agent_name == name,
            DiscoveredAgent.available.is_(True),
        )
    )
    agents = result.scalars().all()
    return [
        {
            "workspace_server_id": a.workspace_server_id,
            "version": a.version,
            "path": a.path,
        }
        for a in agents
    ]