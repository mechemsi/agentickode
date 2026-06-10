# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook endpoints for issue-based task sources.

Parses Plane, GitHub, Gitea, and GitLab issue webhooks, looks up project config,
and creates a task_run row for the worker to pick up.
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import ProjectConfig, TaskRun
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.services.run_factory import create_task_run, resolve_workspace_path
from backend.services.triggers import TriggerEvent, TriggerMatcher

logger = logging.getLogger("agentickode.webhooks")
router = APIRouter(tags=["webhooks"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> ProjectConfigRepository:
    return ProjectConfigRepository(db)


# Re-export for backwards compatibility with webhooks_pr.py and tests
_create_task_run = create_task_run
_resolve_workspace_path = resolve_workspace_path


# Map Plane's event names (issue.created, issue.updated, ...) to the trigger
# schema's action vocabulary. Unknown events fall back to None so the trigger's
# action='any' still matches.
_PLANE_EVENT_TO_ACTION = {
    "issue.created": "opened",
    "issue_created": "opened",
    "issue.updated": "labeled",
    "issue_updated": "labeled",
    "issue.commented": "commented",
    "issue_commented": "commented",
}


def _normalize_action(event: str) -> str | None:
    """Translate provider event names to the trigger-schema action vocab."""
    return _PLANE_EVENT_TO_ACTION.get(event) if event else None


@router.post("/webhooks/plane")
async def plane_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive Plane issue events."""
    body = await request.json()
    data = body.get("data", body)
    event = body.get("event", "")

    labels = data.get("labels", [])
    label_names = [lbl.get("name", "") if isinstance(lbl, dict) else str(lbl) for lbl in labels]
    if "ai-task" not in label_names:
        return {"status": "ignored", "reason": "not_ai_task"}

    task_id = str(data.get("id", ""))
    project_id = str(data.get("project", ""))
    title = data.get("name", "")
    description = data.get("description_html") or data.get("description", "")

    if not task_id or not project_id:
        return {"status": "ignored", "reason": "missing_ids"}

    project = await repo.get_by_id(project_id)
    if not project:
        logger.warning(f"No project config for project_id={project_id}")
        return {"status": "ignored", "reason": "unknown_project"}

    matched_flow = await TriggerMatcher(db).match(
        TriggerEvent(
            type="issue_event",
            source="plane",
            labels=label_names,
            action=_normalize_action(event),
        )
    )

    run = _create_task_run(
        task_id=task_id,
        project=project,
        title=title,
        description=description,
        task_source="plane",
        task_source_meta={
            "workspace_slug": data.get("workspace_detail", {}).get("slug", ""),
            "state_group": data.get("state_detail", {}).get("group", ""),
            "event": event,
            "labels": label_names,
        },
        use_claude="use-claude" in label_names,
        flow_prompt_id=matched_flow.id if matched_flow else None,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info(f"Created run #{run.id} from Plane webhook: {title}")
    return {"status": "accepted", "run_id": run.id}


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive GitHub issue events."""
    body = await request.json()
    action = body.get("action", "")
    issue = body.get("issue", {})

    if action not in ("opened", "labeled"):
        return {"status": "ignored", "reason": f"action_{action}"}

    labels = issue.get("labels", [])
    label_names = [lbl.get("name", "") for lbl in labels]
    if "ai-task" not in label_names:
        return {"status": "ignored", "reason": "not_ai_task"}

    repo_data = body.get("repository", {})
    repo_full_name = repo_data.get("full_name", "")
    owner, name = repo_full_name.split("/", 1) if "/" in repo_full_name else ("", repo_full_name)

    project = await repo.get_by_git_repo("github", owner, name)
    if not project:
        project = await repo.get_by_id(repo_full_name)
    if not project:
        logger.warning(f"No project config for {repo_full_name}")
        return {"status": "ignored", "reason": "unknown_project"}

    task_id = str(issue.get("number", ""))
    matched_flow = await TriggerMatcher(db).match(
        TriggerEvent(
            type="issue_event",
            source="github",
            labels=label_names,
            action=action or None,
        )
    )

    run = _create_task_run(
        task_id=task_id,
        project=project,
        title=issue.get("title", ""),
        description=issue.get("body", ""),
        task_source="github",
        task_source_meta={
            "issue_number": issue.get("number"),
            "repo_full_name": repo_full_name,
            "labels": label_names,
        },
        use_claude="use-claude" in label_names,
        flow_prompt_id=matched_flow.id if matched_flow else None,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info(f"Created run #{run.id} from GitHub webhook: {run.title}")
    return {"status": "accepted", "run_id": run.id}


@router.post("/webhooks/gitea")
async def gitea_issue_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive Gitea issue events."""
    body = await request.json()
    action = body.get("action", "")
    issue = body.get("issue", {})

    if action not in ("opened", "labeled"):
        return {"status": "ignored", "reason": f"action_{action}"}

    labels = issue.get("labels", [])
    label_names = [lbl.get("name", "") for lbl in labels]
    if "ai-task" not in label_names:
        return {"status": "ignored", "reason": "not_ai_task"}

    repo_data = body.get("repository", {})
    repo_full_name = repo_data.get("full_name", "")
    owner, name = repo_full_name.split("/", 1) if "/" in repo_full_name else ("", repo_full_name)

    project = await repo.get_by_git_repo("gitea", owner, name)
    if not project:
        logger.warning(f"No project config for {repo_full_name}")
        return {"status": "ignored", "reason": "unknown_project"}

    task_id = str(issue.get("number", ""))
    matched_flow = await TriggerMatcher(db).match(
        TriggerEvent(
            type="issue_event",
            source="gitea",
            labels=label_names,
            action=action or None,
        )
    )

    run = _create_task_run(
        task_id=task_id,
        project=project,
        title=issue.get("title", ""),
        description=issue.get("body", ""),
        task_source="gitea",
        task_source_meta={
            "issue_number": issue.get("number"),
            "repo_full_name": repo_full_name,
            "labels": label_names,
        },
        use_claude="use-claude" in label_names,
        flow_prompt_id=matched_flow.id if matched_flow else None,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info(f"Created run #{run.id} from Gitea webhook: {run.title}")
    return {"status": "accepted", "run_id": run.id}


@router.post("/webhooks/gitlab")
async def gitlab_issue_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive GitLab issue events."""
    body = await request.json()
    if body.get("object_kind", "") != "issue":
        return {"status": "ignored", "reason": f"object_kind_{body.get('object_kind', '')}"}

    attrs = body.get("object_attributes", {})
    action = attrs.get("action", "")
    if action not in ("open", "update"):
        return {"status": "ignored", "reason": f"action_{action}"}

    labels = body.get("labels", [])
    label_names = [lbl.get("title", "") for lbl in labels]
    if "ai-task" not in label_names:
        return {"status": "ignored", "reason": "not_ai_task"}

    project_data = body.get("project", {})
    repo_full_name = project_data.get("path_with_namespace", "")
    owner, name = repo_full_name.split("/", 1) if "/" in repo_full_name else ("", repo_full_name)

    project = await repo.get_by_git_repo("gitlab", owner, name)
    if not project:
        logger.warning(f"No project config for {repo_full_name}")
        return {"status": "ignored", "reason": "unknown_project"}

    task_id = str(attrs.get("iid", ""))
    # GitLab uses 'open'/'update'; normalize to the trigger schema's vocab
    # so triggers configured with action='opened'/'labeled' line up.
    gitlab_action = {"open": "opened", "update": "labeled"}.get(action) or action or None
    matched_flow = await TriggerMatcher(db).match(
        TriggerEvent(
            type="issue_event",
            source="gitlab",
            labels=label_names,
            action=gitlab_action,
        )
    )

    run = _create_task_run(
        task_id=task_id,
        project=project,
        title=attrs.get("title", ""),
        description=attrs.get("description", ""),
        task_source="gitlab",
        task_source_meta={
            "issue_iid": attrs.get("iid"),
            "issue_url": attrs.get("url", ""),
            "repo_full_name": repo_full_name,
            "labels": label_names,
        },
        use_claude="use-claude" in label_names,
        flow_prompt_id=matched_flow.id if matched_flow else None,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info(f"Created run #{run.id} from GitLab webhook: {run.title}")
    return {"status": "accepted", "run_id": run.id}


_NOTION_AI_TASK_TAG = "ai-task"
_NOTION_USE_CLAUDE_TAG = "use-claude"


def _notion_multi_select(prop: dict | None) -> list[str]:
    if not isinstance(prop, dict):
        return []
    return [opt.get("name", "") for opt in prop.get("multi_select", []) or []]


def _notion_title_text(prop: dict | None) -> str:
    if not isinstance(prop, dict):
        return ""
    return "".join(chunk.get("plain_text", "") for chunk in prop.get("title", []) or [])


async def _project_for_notion_database(db: AsyncSession, database_id: str) -> ProjectConfig | None:
    """Find the project whose integration_config.notion_database_id matches.

    Does the match in Python so the query stays portable across PostgreSQL
    and SQLite (used in tests).
    """
    stmt = (
        select(ProjectConfig)
        .options(selectinload(ProjectConfig.workspace_servers))
        .where(ProjectConfig.task_source == "notion")
    )
    result = await db.execute(stmt)
    for project in result.scalars().all():
        cfg = project.integration_config or {}
        if cfg.get("notion_database_id") == database_id:
            return project
    return None


@router.post("/webhooks/notion")
async def notion_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive Notion page events from a database with ai-task tagging.

    Handles Notion's initial subscription verification by echoing the
    ``verification_token`` field when it is present.
    """
    body = await request.json()

    # Notion subscription verification handshake.
    verification_token = body.get("verification_token")
    if verification_token and "event" not in body and "page" not in body:
        return {"verification_token": verification_token}

    # Support both top-level ``page`` payloads and the event wrapper used by
    # Notion's webhook deliveries (``{"type": "...", "page": {...}}``).
    event_type = body.get("event") or body.get("type", "")
    page = body.get("page") or body.get("data") or {}
    if not isinstance(page, dict) or not page.get("id"):
        return {"status": "ignored", "reason": "no_page"}

    parent = page.get("parent", {}) or {}
    database_id = parent.get("database_id") or page.get("database_id") or ""
    if not database_id:
        return {"status": "ignored", "reason": "no_database"}

    project = await _project_for_notion_database(db, database_id)
    if not project:
        logger.warning("No Notion project config for database %s", database_id)
        return {"status": "ignored", "reason": "unknown_project"}

    cfg = project.integration_config or {}
    tag_property = cfg.get("notion_tag_property", "Tags")
    title_property = cfg.get("notion_title_property", "Name")
    status_property = cfg.get("notion_status_property", "Status")
    ai_task_tag = cfg.get("notion_ai_task_tag", _NOTION_AI_TASK_TAG)
    use_claude_tag = cfg.get("notion_use_claude_tag", _NOTION_USE_CLAUDE_TAG)

    props = page.get("properties", {}) or {}
    tags = _notion_multi_select(props.get(tag_property))
    if ai_task_tag not in tags:
        return {"status": "ignored", "reason": "not_ai_task"}

    title = _notion_title_text(props.get(title_property))
    status_prop = props.get(status_property) or {}
    status_value = ""
    if isinstance(status_prop, dict):
        sel = status_prop.get("select") or status_prop.get("status")
        if isinstance(sel, dict):
            status_value = sel.get("name", "")

    # Dedupe: if a run already exists for this page, ignore
    existing = await db.execute(
        select(TaskRun.id).where(
            TaskRun.project_id == project.project_id,
            TaskRun.task_source == "notion",
            TaskRun.task_id == page["id"],
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "ignored", "reason": "duplicate"}

    matched_flow = await TriggerMatcher(db).match(
        TriggerEvent(type="label", source="notion", labels=tags)
    )

    run = _create_task_run(
        task_id=page["id"],
        project=project,
        title=title,
        description=page.get("url", ""),
        task_source="notion",
        task_source_meta={
            "database_id": database_id,
            "page_id": page["id"],
            "url": page.get("url", ""),
            "tags": tags,
            "status": status_value,
            "status_property": status_property,
            "title_property": title_property,
            "event": event_type,
        },
        use_claude=use_claude_tag in tags,
        flow_prompt_id=matched_flow.id if matched_flow else None,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info("Created run #%d from Notion webhook: %s", run.id, title)
    return {"status": "accepted", "run_id": run.id}
