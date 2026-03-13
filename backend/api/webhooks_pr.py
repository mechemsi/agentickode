# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook endpoints for pull-request events.

Parses GitHub and Gitea pull_request webhooks, looks up project config,
and creates a pr-review task_run row for the worker to pick up.
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.webhooks import _create_task_run, _get_repo
from backend.database import get_db
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.workflow_template_repo import WorkflowTemplateRepository

logger = logging.getLogger("agentickode.webhooks")
router = APIRouter(tags=["webhooks"])


async def _get_pr_review_template_id(db: AsyncSession) -> int | None:
    wf_repo = WorkflowTemplateRepository(db)
    template = await wf_repo.get_by_name("pr-review")
    return int(template.id) if template else None


@router.post("/webhooks/github-pr")
async def github_pr_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive GitHub pull_request events and create pr-review task runs."""
    body = await request.json()
    action = body.get("action", "")

    if action not in ("opened", "synchronize"):
        return {"status": "ignored", "reason": f"action_{action}"}

    pr = body.get("pull_request", {})
    repo_data = body.get("repository", {})
    repo_full_name = repo_data.get("full_name", "")
    owner, name = repo_full_name.split("/", 1) if "/" in repo_full_name else ("", repo_full_name)

    project = await repo.get_by_git_repo("github", owner, name)
    if not project:
        logger.warning(f"No project config for {repo_full_name}")
        return {"status": "ignored", "reason": "unknown_project"}

    pr_number = pr.get("number", 0)
    pr_title = pr.get("title", "")
    pr_url = pr.get("html_url", "")
    template_id = await _get_pr_review_template_id(db)

    run = _create_task_run(
        task_id=f"pr-{pr_number}",
        project=project,
        title=f"Review PR #{pr_number}: {pr_title}",
        description=pr.get("body", "") or "",
        task_source="github",
        task_source_meta={
            "pr_url": pr_url,
            "pr_number": pr_number,
            "pr_title": pr_title,
            "pr_head_branch": pr.get("head", {}).get("ref", ""),
            "repo_full_name": repo_full_name,
            "labels": [lbl.get("name", "") for lbl in pr.get("labels", [])],
        },
        use_claude=False,
    )
    run.workflow_template_id = template_id
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info(f"Created run #{run.id} from GitHub PR webhook: {run.title}")
    return {"status": "accepted", "run_id": run.id}


@router.post("/webhooks/gitea-pr")
async def gitea_pr_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive Gitea pull_request events and create pr-review task runs."""
    body = await request.json()
    action = body.get("action", "")

    if action not in ("opened", "synchronized"):
        return {"status": "ignored", "reason": f"action_{action}"}

    pr = body.get("pull_request", {})
    repo_data = body.get("repository", {})
    repo_full_name = repo_data.get("full_name", "")
    owner, name = repo_full_name.split("/", 1) if "/" in repo_full_name else ("", repo_full_name)

    project = await repo.get_by_git_repo("gitea", owner, name)
    if not project:
        logger.warning(f"No project config for {repo_full_name}")
        return {"status": "ignored", "reason": "unknown_project"}

    pr_number = pr.get("number", 0)
    pr_title = pr.get("title", "")
    pr_url = pr.get("html_url", "")
    template_id = await _get_pr_review_template_id(db)

    run = _create_task_run(
        task_id=f"pr-{pr_number}",
        project=project,
        title=f"Review PR #{pr_number}: {pr_title}",
        description=pr.get("body", "") or "",
        task_source="gitea",
        task_source_meta={
            "pr_url": pr_url,
            "pr_number": pr_number,
            "pr_title": pr_title,
            "pr_head_branch": pr.get("head", {}).get("ref", ""),
            "repo_full_name": repo_full_name,
            "labels": [lbl.get("name", "") for lbl in pr.get("labels", [])],
        },
        use_claude=False,
    )
    run.workflow_template_id = template_id
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info(f"Created run #{run.id} from Gitea PR webhook: {run.title}")
    return {"status": "accepted", "run_id": run.id}
