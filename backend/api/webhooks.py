# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook endpoints for issue-based task sources.

Parses Plane, GitHub, Gitea, and GitLab issue webhooks, looks up project config,
and creates a task_run row for the worker to pick up.
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ProjectConfig, TaskRun
from backend.repositories.project_config_repo import ProjectConfigRepository

logger = logging.getLogger("agentickode.webhooks")
router = APIRouter(tags=["webhooks"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> ProjectConfigRepository:
    return ProjectConfigRepository(db)


def _resolve_workspace_path(project: ProjectConfig, task_id: str) -> str:
    ws_cfg = project.workspace_config or {}
    ws_type = ws_cfg.get("workspace_type", "existing")
    if ws_type == "cluster":
        return f"/workspaces/{task_id}"
    if project.workspace_path:
        return str(project.workspace_path)
    return f"/workspaces/{project.project_id}"


def _create_task_run(
    task_id: str,
    project: ProjectConfig,
    title: str,
    description: str,
    task_source: str,
    task_source_meta: dict,
    use_claude: bool,
) -> TaskRun:
    return TaskRun(
        task_id=task_id,
        project_id=project.project_id,
        title=title,
        description=description,
        branch_name=f"feature/ai-{task_id}",
        workspace_path=_resolve_workspace_path(project, task_id),
        repo_owner=project.repo_owner,
        repo_name=project.repo_name,
        default_branch=project.default_branch,
        task_source=task_source,
        git_provider=project.git_provider,
        task_source_meta=task_source_meta,
        use_claude_api=use_claude,
        workspace_config=project.workspace_config,
    )


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
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info(f"Created run #{run.id} from GitLab webhook: {run.title}")
    return {"status": "accepted", "run_id": run.id}
