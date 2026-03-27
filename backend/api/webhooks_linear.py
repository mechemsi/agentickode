# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook endpoint for Linear issue events."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.services.run_factory import create_task_run

logger = logging.getLogger("agentickode.webhooks.linear")
router = APIRouter(tags=["webhooks"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> ProjectConfigRepository:
    return ProjectConfigRepository(db)


@router.post("/webhooks/linear")
async def linear_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive Linear issue events (create, update with ai-task label)."""
    body = await request.json()
    action = body.get("action", "")
    data = body.get("data", {})

    if body.get("type") != "Issue":
        return {"status": "ignored", "reason": "not_issue"}

    if action not in ("create", "update"):
        return {"status": "ignored", "reason": f"action_{action}"}

    # Check for ai-task label
    labels = data.get("labels", [])
    label_names = [lbl.get("name", "") if isinstance(lbl, dict) else str(lbl) for lbl in labels]
    if "ai-task" not in label_names:
        return {"status": "ignored", "reason": "not_ai_task"}

    # Linear provides team key and issue identifier
    issue_id = data.get("id", "")
    identifier = data.get("identifier", "")  # e.g. "ENG-123"
    title = data.get("title", "")
    description = data.get("description") or ""
    team = data.get("team", {})
    team_key = team.get("key", "") if isinstance(team, dict) else ""

    if not issue_id:
        return {"status": "ignored", "reason": "missing_issue_id"}

    # Try to find project by Linear team key or identifier prefix
    project = await repo.get_by_id(team_key) if team_key else None
    if not project and identifier:
        prefix = identifier.split("-")[0]
        project = await repo.get_by_id(prefix)
    if not project:
        logger.warning("No project config for Linear team %s", team_key)
        return {"status": "ignored", "reason": "unknown_project"}

    run = create_task_run(
        task_id=identifier or issue_id,
        project=project,
        title=title,
        description=description,
        task_source="linear",
        task_source_meta={
            "linear_issue_id": issue_id,
            "identifier": identifier,
            "team_key": team_key,
            "labels": label_names,
        },
        use_claude="use-claude" in label_names,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info("Created run #%d from Linear webhook: %s", run.id, title)
    return {"status": "accepted", "run_id": run.id}
