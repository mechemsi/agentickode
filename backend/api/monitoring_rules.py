# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CRUD endpoints for monitoring rules."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.agents import MonitoringRule
from backend.repositories.monitoring_rule_repo import MonitoringRuleRepository
from backend.schemas.monitoring import (
    MonitoringRuleCreate,
    MonitoringRuleOut,
    MonitoringRuleUpdate,
)

logger = logging.getLogger("agentickode.api.monitoring_rules")
router = APIRouter(tags=["monitoring-rules"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> MonitoringRuleRepository:
    return MonitoringRuleRepository(db)


@router.get("/projects/{project_id}/monitoring-rules", response_model=list[MonitoringRuleOut])
async def list_monitoring_rules(
    project_id: str,
    repo: MonitoringRuleRepository = Depends(_get_repo),
):
    return await repo.list_by_project(project_id)


@router.post("/projects/{project_id}/monitoring-rules", response_model=MonitoringRuleOut)
async def create_monitoring_rule(
    project_id: str,
    body: MonitoringRuleCreate,
    db: AsyncSession = Depends(get_db),
    repo: MonitoringRuleRepository = Depends(_get_repo),
):
    rule = MonitoringRule(
        project_id=project_id,
        source=body.source,
        min_severity=body.min_severity,
        task_template=body.task_template,
        enabled=body.enabled,
    )
    rule = await repo.create(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/monitoring-rules/{rule_id}", response_model=MonitoringRuleOut)
async def update_monitoring_rule(
    rule_id: int,
    body: MonitoringRuleUpdate,
    db: AsyncSession = Depends(get_db),
    repo: MonitoringRuleRepository = Depends(_get_repo),
):
    rule = await repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(404, "Monitoring rule not found")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)

    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/monitoring-rules/{rule_id}")
async def delete_monitoring_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    repo: MonitoringRuleRepository = Depends(_get_repo),
):
    rule = await repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(404, "Monitoring rule not found")
    await repo.delete(rule)
    await db.commit()
    return {"status": "deleted"}
