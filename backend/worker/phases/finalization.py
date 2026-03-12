# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 6: Finalization — confirm PR is open, cleanup sandbox.

The PR is created during the approval phase. Finalization does NOT auto-merge;
the human reviewer merges via the git provider UI after reviewing the PR.

For pr-review workflows, posts the AI review as a comment on the source PR.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps, get_git_provider
from backend.services.git.ops import get_repo_https_url
from backend.services.http_client import get_http_client
from backend.services.workspace.sandbox import RemoteSandbox
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._helpers import (
    close_run_session,
    get_auth_url,
    get_project_token,
    get_ssh_for_run,
)

logger = logging.getLogger("autodev.phases.finalization")

PHASE_META = {
    "description": "Confirm PR and clean up resources",
}


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> None:
    meta = task_run.task_source_meta or {}
    pr_number = meta.get("pr_number")
    pr_branch = meta.get("pr_head_branch")

    # fix-pr: push fixes to existing PR branch (no new PR)
    if pr_branch and not task_run.pr_url:
        await _push_to_pr_branch(task_run, pr_branch, session)

    # Post review comment on source PR for pr-review / fix-pr workflows
    if task_run.review_result and pr_number:
        await _post_review_comment(task_run, pr_number, session)

    if task_run.pr_url:
        await broadcaster.log(
            task_run.id,
            f"PR ready for human review: {task_run.pr_url}",
            phase="finalization",
        )
    elif not pr_number:
        await broadcaster.log(task_run.id, "No PR URL found", level="warning", phase="finalization")

    # Close agent session (release locks so session_id can be reused if needed)
    await close_run_session(task_run, session)

    # Cleanup workspace
    await broadcaster.log(task_run.id, "Stopping sandbox containers (if any)", phase="finalization")
    ssh = await get_ssh_for_run(task_run, session)
    remote_sandbox = RemoteSandbox(ssh)
    await remote_sandbox.stop_sandbox(task_run.workspace_path)
    await broadcaster.log(task_run.id, "Cleanup complete", phase="finalization")


async def _push_to_pr_branch(task_run: TaskRun, pr_branch: str, session: AsyncSession) -> None:
    """Push fixes to the existing PR branch."""
    await broadcaster.log(
        task_run.id,
        f"Pushing fixes to PR branch {pr_branch}",
        phase="finalization",
    )
    ssh = await get_ssh_for_run(task_run, session)
    remote_git = RemoteGitOps(ssh)

    project_token = await get_project_token(task_run, session)
    base_url = get_repo_https_url(task_run.git_provider, task_run.repo_owner, task_run.repo_name)

    auth_url, method = await get_auth_url(
        base_url, task_run.git_provider, ssh, token_override=project_token
    )
    cwd = task_run.workspace_path
    await remote_git.run_git(["remote", "set-url", "origin", auth_url], cwd=cwd)
    await remote_git.run_git(["push", "origin", pr_branch], cwd=cwd)
    await broadcaster.log(
        task_run.id,
        f"Pushed to {pr_branch} (auth={method})",
        phase="finalization",
    )


async def _post_review_comment(task_run: TaskRun, pr_number: int, session: AsyncSession) -> None:
    """Post AI review results as a comment on the source PR."""
    repo_path = f"{task_run.repo_owner}/{task_run.repo_name}"
    body = _build_review_comment(task_run.review_result)

    project_token = await get_project_token(task_run, session)
    client = get_http_client()
    provider = get_git_provider(task_run.git_provider, client, access_token=project_token)
    try:
        await provider.post_pr_comment(repo_path, pr_number, body)
        await broadcaster.log(
            task_run.id,
            f"Posted review comment on PR #{pr_number}",
            phase="finalization",
        )
    except Exception as exc:
        await broadcaster.log(
            task_run.id,
            f"Failed to post review comment: {exc}",
            level="warning",
            phase="finalization",
        )


def _build_review_comment(review: dict) -> str:
    """Build a markdown comment from the review result."""
    issues = review.get("issues", [])
    suggestions = review.get("suggestions", [])
    summary = review.get("summary", "")
    approved = review.get("approved", False)

    parts = ["## AI Code Review\n"]

    if summary:
        parts.append(f"{summary}\n")

    status = "Approved" if approved else "Changes Requested"
    parts.append(f"**Status**: {status}")
    parts.append(f"**Issues Found**: {len(issues)}")
    parts.append(f"**Suggestions**: {len(suggestions)}\n")

    if issues:
        parts.append("### Issues\n")
        for issue in issues:
            severity = issue.get("severity", "info")
            desc = issue.get("description", "")
            file = issue.get("file", "")
            line = issue.get("line", "")
            loc = f"`{file}:{line}`" if file and line else (f"`{file}`" if file else "")
            parts.append(f"- **[{severity}]** {loc} {desc}")
        parts.append("")

    if suggestions:
        parts.append("### Suggestions\n")
        for s in suggestions:
            if isinstance(s, dict):
                parts.append(f"- {s.get('description', str(s))}")
            else:
                parts.append(f"- {s}")
        parts.append("")

    parts.append("---")
    parts.append("*Generated by AI Development Infrastructure*")
    return "\n".join(parts)