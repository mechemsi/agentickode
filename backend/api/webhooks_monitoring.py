# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook endpoints for monitoring/error-tracking sources.

Parses Sentry, Datadog, Grafana, and PagerDuty webhooks, matches against
MonitoringRule configs, and creates task runs for auto-investigation.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.agents import MonitoringRule
from backend.repositories.monitoring_rule_repo import MonitoringRuleRepository
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.services.monitoring.payload_parsers import (
    MonitoringEvent,
    parse_datadog_payload,
    parse_grafana_payload,
    parse_pagerduty_payload,
    parse_sentry_payload,
)
from backend.services.monitoring.severity import meets_threshold
from backend.services.run_factory import create_task_run

logger = logging.getLogger("agentickode.webhooks.monitoring")
router = APIRouter(tags=["webhooks-monitoring"])


def _get_monitoring_repo(db: AsyncSession = Depends(get_db)) -> MonitoringRuleRepository:
    return MonitoringRuleRepository(db)


def _get_project_repo(db: AsyncSession = Depends(get_db)) -> ProjectConfigRepository:
    return ProjectConfigRepository(db)


async def _dispatch_monitoring_event(
    event: MonitoringEvent,
    db: AsyncSession,
    monitoring_repo: MonitoringRuleRepository,
    project_repo: ProjectConfigRepository,
) -> dict:
    """Match event against monitoring rules and create runs."""
    rules = await monitoring_repo.list_by_source(event.source)
    if not rules:
        return {"status": "ignored", "reason": "no_matching_rules"}

    created_runs = []
    for rule in rules:
        if not meets_threshold(event.severity, rule.min_severity):
            continue

        # Dedup: skip if triggered recently (within 1 hour by default)
        if _is_dedup_blocked(rule):
            logger.debug("Rule %d dedup blocked for '%s'", rule.id, event.title)
            continue

        project = await project_repo.get_by_id(rule.project_id)
        if not project:
            continue

        task_id = f"mon-{rule.id}-{uuid.uuid4().hex[:8]}"
        description = f"{rule.task_template}\n\n---\n\n{event.description}"

        run = create_task_run(
            task_id=task_id,
            project=project,
            title=f"[{event.source.title()}] {event.title[:100]}",
            description=description,
            task_source=event.source,
            task_source_meta={
                "monitoring_rule_id": rule.id,
                "severity": event.severity,
                "source_url": event.url,
                "project_hint": event.project_hint,
            },
        )
        db.add(run)
        await db.flush()
        created_runs.append(run.id)

        # Update dedup timestamp
        rule.last_triggered_at = datetime.now(UTC)
        logger.info(
            "Monitoring rule %d dispatched run #%d for '%s' (%s)",
            rule.id,
            run.id,
            event.title,
            event.severity,
        )

    if created_runs:
        await db.commit()
        return {"status": "accepted", "run_ids": created_runs}

    return {"status": "ignored", "reason": "below_threshold_or_dedup"}


def _is_dedup_blocked(rule: MonitoringRule) -> bool:
    """Check if rule was triggered too recently."""
    if not hasattr(rule, "last_triggered_at") or not rule.last_triggered_at:
        return False
    dedup_window = getattr(rule, "dedup_window_seconds", 3600) or 3600
    elapsed = (datetime.now(UTC) - rule.last_triggered_at).total_seconds()
    return elapsed < dedup_window


@router.post("/webhooks/sentry")
async def sentry_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    monitoring_repo: MonitoringRuleRepository = Depends(_get_monitoring_repo),
    project_repo: ProjectConfigRepository = Depends(_get_project_repo),
):
    """Receive Sentry issue/event alert webhooks."""
    body = await request.json()
    event = parse_sentry_payload(body)
    return await _dispatch_monitoring_event(event, db, monitoring_repo, project_repo)


@router.post("/webhooks/datadog")
async def datadog_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    monitoring_repo: MonitoringRuleRepository = Depends(_get_monitoring_repo),
    project_repo: ProjectConfigRepository = Depends(_get_project_repo),
):
    """Receive Datadog webhook notifications."""
    body = await request.json()
    event = parse_datadog_payload(body)
    return await _dispatch_monitoring_event(event, db, monitoring_repo, project_repo)


@router.post("/webhooks/grafana")
async def grafana_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    monitoring_repo: MonitoringRuleRepository = Depends(_get_monitoring_repo),
    project_repo: ProjectConfigRepository = Depends(_get_project_repo),
):
    """Receive Grafana unified alerting webhooks."""
    body = await request.json()
    event = parse_grafana_payload(body)
    return await _dispatch_monitoring_event(event, db, monitoring_repo, project_repo)


@router.post("/webhooks/pagerduty")
async def pagerduty_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    monitoring_repo: MonitoringRuleRepository = Depends(_get_monitoring_repo),
    project_repo: ProjectConfigRepository = Depends(_get_project_repo),
):
    """Receive PagerDuty v3 webhook events."""
    body = await request.json()
    event = parse_pagerduty_payload(body)
    return await _dispatch_monitoring_event(event, db, monitoring_repo, project_repo)
