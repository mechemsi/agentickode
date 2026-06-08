# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Shared helpers for the PR-review webhook + CI trigger endpoints."""

import json
import logging

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ProjectConfig, TaskRun
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.services.run_factory import create_task_run
from backend.services.triggers import TriggerEvent, TriggerMatcher
from backend.services.webhook_security import verify_hmac_sha256

logger = logging.getLogger("agentickode.webhooks")

# PR actions worth reviewing (others — e.g. closed/assigned — are ignored).
GITHUB_PR_ACTIONS = {"opened", "synchronize", "reopened", "labeled", "ready_for_review"}
GITEA_PR_ACTIONS = {"opened", "synchronized", "reopened", "label_updated"}

# Statuses for which a review is still in-flight (used to dedupe rapid PR events).
_ACTIVE_RUN_STATUSES = ("pending", "running")


async def read_verified_body(request: Request, secret: str, signature_header: str) -> dict:
    """Read the raw body, verifying the HMAC signature when a secret is set."""
    raw = await request.body()
    if secret and not verify_hmac_sha256(secret, raw, request.headers.get(signature_header)):
        raise HTTPException(status_code=401, detail="invalid webhook signature")
    try:
        return json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON body") from exc


async def _active_review_exists(db: AsyncSession, project_id: str, task_id: str) -> bool:
    """True if a review run for this project + PR is already pending/running."""
    result = await db.execute(
        select(TaskRun.id).where(
            TaskRun.project_id == project_id,
            TaskRun.task_id == task_id,
            TaskRun.status.in_(_ACTIVE_RUN_STATUSES),
        )
    )
    return result.scalar_one_or_none() is not None


def build_pr_review_run(
    project: ProjectConfig,
    *,
    task_source: str,
    pr_number: int,
    pr_title: str,
    pr_body: str,
    pr_head_branch: str,
    pr_url: str,
    repo_full_name: str,
    labels: list[str],
    template_id: int,
    pr_head_sha: str = "",
) -> TaskRun:
    """Create a single-pass, comment-mode PR-review run bound to a template."""
    run = create_task_run(
        task_id=f"pr-{pr_number}",
        project=project,
        title=f"Review PR #{pr_number}: {pr_title}",
        description=pr_body or "",
        task_source=task_source,
        task_source_meta={
            "pr_url": pr_url,
            "pr_number": pr_number,
            "pr_title": pr_title,
            "pr_head_branch": pr_head_branch,
            "pr_head_sha": pr_head_sha,
            "repo_full_name": repo_full_name,
            "labels": labels,
            "review_mode": "comment",
        },
        use_claude=False,
        workflow_template_id=template_id,
    )
    run.max_retries = 0  # single-pass review — never auto-fix an un-checked-out workspace
    return run


async def handle_pr_event(
    request: Request,
    db: AsyncSession,
    repo: ProjectConfigRepository,
    *,
    source: str,
    allowed_actions: set[str],
    secret: str,
    signature_header: str,
) -> dict:
    """Parse a provider ``pull_request`` event and launch a review when matched."""
    body = await read_verified_body(request, secret, signature_header)
    action = body.get("action", "")
    if action not in allowed_actions:
        return {"status": "ignored", "reason": f"action_{action}"}

    pr = body.get("pull_request", {})
    repo_full_name = body.get("repository", {}).get("full_name", "")
    owner, name = repo_full_name.split("/", 1) if "/" in repo_full_name else ("", repo_full_name)

    project = await repo.get_by_git_repo(source, owner, name)
    if not project:
        project = await repo.get_by_id(repo_full_name)  # parity with issue webhook
    if not project:
        logger.warning("No project config for %s", repo_full_name)
        return {"status": "ignored", "reason": "unknown_project"}

    label_names = [lbl.get("name", "") for lbl in pr.get("labels", [])]
    template = await TriggerMatcher(db).match(
        TriggerEvent(type="pr_event", source=source, labels=label_names, action=action or None)
    )
    if not template:
        return {"status": "ignored", "reason": "no_matching_template"}

    pr_number = pr.get("number", 0)
    if await _active_review_exists(db, project.project_id, f"pr-{pr_number}"):
        logger.info("Review already in-flight for %s PR #%s — skipping", source, pr_number)
        return {"status": "ignored", "reason": "review_in_progress"}

    run = build_pr_review_run(
        project,
        task_source=source,
        pr_number=pr_number,
        pr_title=pr.get("title", ""),
        pr_body=pr.get("body", "") or "",
        pr_head_branch=pr.get("head", {}).get("ref", ""),
        pr_url=pr.get("html_url", ""),
        repo_full_name=repo_full_name,
        labels=label_names,
        template_id=template.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info("Created run #%d from %s PR webhook: %s", run.id, source, run.title)
    return {"status": "accepted", "run_id": run.id}
