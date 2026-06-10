# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook-less PR review polling.

For a local server with no public webhook domain, poll git providers outbound for
open PRs labelled ``ai-review`` (or already ``ai-reviewed``) and launch a review run.
A PR is reviewed once; the PR head commit SHA stored on the review ``TaskRun`` is the
dedup key. Automatic re-review on new commits is **opt-in per project** via
``ProjectConfig.integration_config['pr_review_rereview_on_push']`` (default off).
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api._pr_webhook_helpers import build_pr_review_run, resolve_pr_review_flow_prompt_id
from backend.models import ProjectConfig, TaskRun
from backend.repositories.git_connection_repo import GitConnectionRepository
from backend.services.encryption import decrypt_value
from backend.services.git.protocol import get_git_provider
from backend.services.http_client import get_http_client

logger = logging.getLogger("agentickode.polling.pr_review")

_AI_REVIEW_LABEL = "ai-review"
_AI_REVIEWED_LABEL = "ai-reviewed"
# Providers that support PR labels (so the ai-review opt-in + flip can work).
_SUPPORTED_PROVIDERS = {"github", "gitea", "gitlab"}
_INFLIGHT_STATUSES = {"pending", "running"}


async def _already_handled(
    session: AsyncSession,
    project_id: str,
    task_id: str,
    head_sha: str,
    rereview_on_push: bool,
) -> bool:
    """Decide whether to skip this PR.

    Skip when a review is in-flight, when this exact head SHA was already attempted,
    or — unless the project opted in via ``rereview_on_push`` — when the PR already has
    *any* prior review (so a new commit does not trigger an automatic re-review).
    """
    result = await session.execute(
        select(TaskRun).where(
            TaskRun.project_id == project_id,
            TaskRun.task_id == task_id,
        )
    )
    runs = list(result.scalars().all())
    if not runs:
        return False  # never reviewed — first review always proceeds
    for run in runs:
        if run.status in _INFLIGHT_STATUSES:
            return True  # a review is already pending/running — never double-start
        if (run.task_source_meta or {}).get("pr_head_sha") == head_sha:
            return True  # this exact commit was already reviewed (or failed) — don't redo
    # The PR has a prior review for a different commit → this would be a re-review.
    # Only allow it when the project is explicitly marked for re-review-on-push.
    return not rereview_on_push


async def _resolve_token(project: ProjectConfig, session: AsyncSession) -> str | None:
    """Resolve the project git token using the same policy as the review phases.

    git_connections (project → global) first, then the legacy encrypted column —
    so the poll half and the finalize half (``get_project_token``) authenticate as
    one identity instead of silently diverging to the global .env token.
    """
    try:
        token = await GitConnectionRepository(session).resolve_token(
            provider=project.git_provider or "github",
            project_id=project.project_id,
        )
        if token:
            return token
    except Exception:
        logger.debug("git_connections lookup failed for %s", project.project_id, exc_info=True)
    if project.git_provider_token_enc:
        try:
            return decrypt_value(project.git_provider_token_enc)
        except Exception:
            logger.warning("Failed to decrypt git token for project %s", project.project_id)
    return None


async def poll_pr_reviews(project: ProjectConfig, session: AsyncSession) -> list[int]:
    """Poll open PRs for a project and create review runs for new ai-review work."""
    if project.git_provider not in _SUPPORTED_PROVIDERS:
        return []
    if not project.repo_owner or not project.repo_name:
        return []

    # ADR-009: PR-review runs the single-agent-call pr_review flow prompt.
    flow_prompt_id = await resolve_pr_review_flow_prompt_id(session)

    token = await _resolve_token(project, session)
    provider = get_git_provider(project.git_provider, get_http_client(), access_token=token)
    repo_path = f"{project.repo_owner}/{project.repo_name}"

    try:
        prs = await provider.list_pull_requests(repo_path, state="open", limit=50)
    except Exception as exc:
        logger.warning("PR poll failed for %s: %s", repo_path, exc)
        return []

    # Per-project opt-in: re-review a PR automatically when new commits are pushed.
    # Off by default — a PR is reviewed once (its first ``ai-review``); re-review only
    # happens for projects explicitly marked for it.
    rereview_on_push = bool((project.integration_config or {}).get("pr_review_rereview_on_push"))

    created: list[int] = []
    for pr in prs:
        labels = pr.get("labels") or []
        if _AI_REVIEW_LABEL not in labels and _AI_REVIEWED_LABEL not in labels:
            continue

        number = pr["number"]
        head_sha = pr.get("head_sha", "")
        task_id = f"pr-{number}"
        if await _already_handled(session, project.project_id, task_id, head_sha, rereview_on_push):
            continue

        run = build_pr_review_run(
            project,
            task_source=project.git_provider,
            pr_number=number,
            pr_title=pr.get("title", ""),
            pr_body=pr.get("body", "") or "",
            pr_head_branch=pr.get("head_ref", ""),
            pr_url=pr.get("html_url", ""),
            repo_full_name=repo_path,
            labels=labels,
            pr_head_sha=head_sha,
            flow_prompt_id=flow_prompt_id,
        )
        session.add(run)
        await session.flush()
        created.append(run.id)
        logger.info("PR poll: created review run #%d for %s#%s", run.id, repo_path, number)

    return created
