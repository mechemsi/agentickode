# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook + CI endpoints that launch AI code-review runs for pull requests.

A PR review is gated by the ``ai-review`` label (GitHub / Gitea ``pull_request``
events) and routed through the ``pr-review`` workflow template via
``TriggerMatcher`` — the same label-driven routing the issue webhooks use. CI
systems can trigger a review directly with ``POST /api/webhooks/pr-review``
(repo + pr_number). Review runs are single-pass (``max_retries=0``) and carry
``review_mode="comment"`` so finalization posts the review instead of pushing.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api._pr_webhook_helpers import (
    GITEA_PR_ACTIONS,
    GITHUB_PR_ACTIONS,
    build_pr_review_run,
    handle_pr_event,
    resolve_pr_review_flow_prompt_id,
)
from backend.api.webhooks import _get_repo
from backend.config import settings
from backend.database import get_db
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.workflow_template_repo import WorkflowTemplateRepository
from backend.services.webhook_security import verify_shared_secret

logger = logging.getLogger("agentickode.webhooks")
router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/github-pr")
async def github_pr_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive GitHub pull_request events; review when labelled ``ai-review``."""
    return await handle_pr_event(
        request,
        db,
        repo,
        source="github",
        allowed_actions=GITHUB_PR_ACTIONS,
        secret=settings.github_webhook_secret,
        signature_header="X-Hub-Signature-256",
    )


@router.post("/webhooks/gitea-pr")
async def gitea_pr_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive Gitea pull_request events; review when labelled ``ai-review``."""
    return await handle_pr_event(
        request,
        db,
        repo,
        source="gitea",
        allowed_actions=GITEA_PR_ACTIONS,
        secret=settings.gitea_webhook_secret,
        signature_header="X-Gitea-Signature",
    )


class PrReviewTriggerRequest(BaseModel):
    """CI-facing payload to launch a review for an existing PR."""

    repo: str  # "owner/name"
    pr_number: int = Field(gt=0)
    provider: str = "github"
    pr_head_branch: str = ""
    pr_title: str = ""
    pr_body: str = ""
    labels: list[str] = []


@router.post("/webhooks/pr-review")
async def trigger_pr_review(
    payload: PrReviewTriggerRequest,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
    x_ci_token: str | None = Header(default=None),
):
    """Launch a PR-review run for ``repo``#``pr_number`` (CI/manual trigger).

    Unlike the webhook, this is an explicit request — it forces the ``pr-review``
    template by name and does not require the ``ai-review`` label. When
    ``CI_TRIGGER_SECRET`` is configured, callers must present a matching
    ``X-CI-Token`` header (constant-time compared); when it is unset the endpoint
    is open (protect it at the network layer).
    """
    if settings.ci_trigger_secret and not verify_shared_secret(
        settings.ci_trigger_secret, x_ci_token
    ):
        raise HTTPException(status_code=401, detail="invalid or missing X-CI-Token")

    owner, _, name = payload.repo.partition("/")
    project = await repo.get_by_git_repo(payload.provider, owner, name)
    if not project:
        raise HTTPException(status_code=404, detail=f"No project for {payload.repo}")

    template = await WorkflowTemplateRepository(db).get_by_name("pr-review")
    if not template:
        raise HTTPException(status_code=503, detail="pr-review template not seeded")

    run = build_pr_review_run(
        project,
        task_source=payload.provider,
        pr_number=payload.pr_number,
        pr_title=payload.pr_title or f"PR #{payload.pr_number}",
        pr_body=payload.pr_body,
        pr_head_branch=payload.pr_head_branch,
        pr_url="",
        repo_full_name=payload.repo,
        labels=payload.labels,
        template_id=template.id,
        flow_prompt_id=await resolve_pr_review_flow_prompt_id(db),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info("Created run #%d from CI pr-review trigger: %s", run.id, run.title)
    return {"status": "accepted", "run_id": run.id}
