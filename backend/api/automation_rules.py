# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CRUD endpoints for automation rules."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.automation_rules import AutomationRule
from backend.repositories.automation_rule_repo import AutomationRuleRepository
from backend.schemas.automation_rules import (
    AutomationRuleCreate,
    AutomationRuleOut,
    AutomationRuleUpdate,
)

logger = logging.getLogger("agentickode.api.automation_rules")
router = APIRouter(tags=["automation-rules"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> AutomationRuleRepository:
    return AutomationRuleRepository(db)


@router.get("/projects/{project_id}/automation-rules", response_model=list[AutomationRuleOut])
async def list_automation_rules(
    project_id: str,
    repo: AutomationRuleRepository = Depends(_get_repo),
):
    return await repo.list_by_project(project_id)


@router.post("/projects/{project_id}/automation-rules", response_model=AutomationRuleOut)
async def create_automation_rule(
    project_id: str,
    body: AutomationRuleCreate,
    db: AsyncSession = Depends(get_db),
    repo: AutomationRuleRepository = Depends(_get_repo),
):
    rule = AutomationRule(
        project_id=project_id,
        name=body.name,
        description=body.description,
        event_source=body.event_source,
        event_filter=body.event_filter,
        action_type=body.action_type,
        action_config=body.action_config,
        cooldown_seconds=body.cooldown_seconds,
        enabled=body.enabled,
    )
    rule = await repo.create(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/automation-rules/{rule_id}", response_model=AutomationRuleOut)
async def update_automation_rule(
    rule_id: int,
    body: AutomationRuleUpdate,
    db: AsyncSession = Depends(get_db),
    repo: AutomationRuleRepository = Depends(_get_repo),
):
    rule = await repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(404, "Automation rule not found")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)

    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/automation-rules/{rule_id}")
async def delete_automation_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    repo: AutomationRuleRepository = Depends(_get_repo),
):
    rule = await repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(404, "Automation rule not found")
    await repo.delete(rule)
    await db.commit()
    return {"status": "deleted"}
