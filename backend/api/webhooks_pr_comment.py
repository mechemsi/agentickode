# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook endpoint for PR review comments that @mention the agent."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.services.run_factory import create_task_run

logger = logging.getLogger("agentickode.webhooks.pr_comment")
router = APIRouter(tags=["webhooks"])

_MENTION_TRIGGERS = {"@agentickode", "@ai-agent", "@autofix"}


def _get_repo(db: AsyncSession = Depends(get_db)) -> ProjectConfigRepository:
    return ProjectConfigRepository(db)


@router.post("/webhooks/github-pr-comment")
async def github_pr_comment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: ProjectConfigRepository = Depends(_get_repo),
):
    """Receive GitHub issue_comment events on PRs with @agentickode mention."""
    body = await request.json()
    action = body.get("action", "")
    if action != "created":
        return {"status": "ignored", "reason": f"action_{action}"}

    comment = body.get("comment", {})
    comment_body = comment.get("body", "")

    # Check if comment mentions the agent
    comment_lower = comment_body.lower()
    if not any(trigger in comment_lower for trigger in _MENTION_TRIGGERS):
        return {"status": "ignored", "reason": "no_mention"}

    # Must be on a PR (issue with pull_request key)
    issue = body.get("issue", {})
    if "pull_request" not in issue:
        return {"status": "ignored", "reason": "not_pr"}

    repo_data = body.get("repository", {})
    repo_full_name = repo_data.get("full_name", "")
    owner, name = repo_full_name.split("/", 1) if "/" in repo_full_name else ("", repo_full_name)

    project = await repo.get_by_git_repo("github", owner, name)
    if not project:
        project = await repo.get_by_id(repo_full_name)
    if not project:
        logger.warning("No project config for %s", repo_full_name)
        return {"status": "ignored", "reason": "unknown_project"}

    pr_number = issue.get("number", "")
    pr_title = issue.get("title", "")
    pr_branch = (issue.get("pull_request") or {}).get("head", {}).get("ref", "")

    # Strip the @mention from the comment to get the actual instruction
    instruction = comment_body
    for trigger in _MENTION_TRIGGERS:
        instruction = instruction.replace(trigger, "").replace(trigger.upper(), "")
    instruction = instruction.strip()
    if not instruction:
        instruction = f"Address the review comment on PR #{pr_number}"

    run = create_task_run(
        task_id=f"pr-comment-{pr_number}-{comment.get('id', '')}",
        project=project,
        title=f"[PR #{pr_number}] {instruction[:80]}",
        description=(
            f"PR review comment on **{pr_title}** (#{pr_number}):\n\n"
            f"> {comment_body}\n\n"
            f"Commenter: {comment.get('user', {}).get('login', 'unknown')}\n"
            f"PR branch: `{pr_branch}`"
        ),
        task_source="github",
        task_source_meta={
            "repo_full_name": repo_full_name,
            "issue_number": pr_number,
            "pr_number": pr_number,
            "pr_branch": pr_branch,
            "comment_id": comment.get("id"),
            "trigger": "pr_comment",
        },
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info("Created run #%d from PR comment on %s#%d", run.id, repo_full_name, pr_number)
    return {"status": "accepted", "run_id": run.id}
