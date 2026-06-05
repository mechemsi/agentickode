# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook-less PR review polling.

For a local server with no public webhook domain, poll git providers outbound for
open PRs labelled ``ai-review`` (or already ``ai-reviewed``) and launch a review run.
The PR's head commit SHA — stored on the review ``TaskRun`` — is the dedup key, so a PR
is reviewed once per head SHA and re-reviewed when new commits are pushed.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api._pr_webhook_helpers import build_pr_review_run
from backend.models import ProjectConfig, TaskRun
from backend.repositories.git_connection_repo import GitConnectionRepository
from backend.repositories.workflow_template_repo import WorkflowTemplateRepository
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
    session: AsyncSession, project_id: str, task_id: str, head_sha: str
) -> bool:
    """True if this PR has an in-flight review, or this head SHA was already attempted."""
    result = await session.execute(
        select(TaskRun).where(
            TaskRun.project_id == project_id,
            TaskRun.task_id == task_id,
        )
    )
    for run in result.scalars().all():
        if run.status in _INFLIGHT_STATUSES:
            return True  # a review is already pending/running — never double-start
        if (run.task_source_meta or {}).get("pr_head_sha") == head_sha:
            return True  # this exact commit was already reviewed (or failed) — don't redo
    return False


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

    template = await WorkflowTemplateRepository(session).get_by_name("pr-review")
    if not template:
        logger.debug("No pr-review template — skipping PR poll for %s", project.project_id)
        return []

    token = await _resolve_token(project, session)
    provider = get_git_provider(project.git_provider, get_http_client(), access_token=token)
    repo_path = f"{project.repo_owner}/{project.repo_name}"

    try:
        prs = await provider.list_pull_requests(repo_path, state="open", limit=50)
    except Exception as exc:
        logger.warning("PR poll failed for %s: %s", repo_path, exc)
        return []

    created: list[int] = []
    for pr in prs:
        labels = pr.get("labels") or []
        if _AI_REVIEW_LABEL not in labels and _AI_REVIEWED_LABEL not in labels:
            continue

        number = pr["number"]
        head_sha = pr.get("head_sha", "")
        task_id = f"pr-{number}"
        if await _already_handled(session, project.project_id, task_id, head_sha):
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
            template_id=template.id,
            pr_head_sha=head_sha,
        )
        session.add(run)
        await session.flush()
        created.append(run.id)
        logger.info("PR poll: created review run #%d for %s#%s", run.id, repo_path, number)

    return created
