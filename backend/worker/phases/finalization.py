# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 6: Finalization — confirm PR is open, cleanup sandbox.

The PR is created during the approval phase. Finalization does NOT auto-merge;
the human reviewer merges via the git provider UI after reviewing the PR.

For pr-review workflows, posts the AI review as a comment on the source PR.
"""

import logging
import shlex

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps, get_git_provider
from backend.services.git.ops import get_repo_https_url
from backend.services.http_client import get_http_client
from backend.services.workspace.sandbox import RemoteSandbox
from backend.services.workspace.worktree import WorktreeManager, WorktreePaths
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._helpers import (
    close_run_session,
    get_auth_url,
    get_project_token,
    get_ssh_for_run,
)

logger = logging.getLogger("agentickode.phases.finalization")

PHASE_META = {
    "kind": "legacy_phase",
    "deprecated_in": "0.5.0",
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

    # Tear down per-run worktree (when workspace_setup created one). We
    # do this BEFORE the generic ``rm -rf`` because rm-ing a registered
    # worktree dir without ``git worktree remove`` leaves the parent
    # repo's ``.git/worktrees/<name>`` admin entry behind — better to let
    # git handle removal cleanly. When ``keep_workspace=true`` on the
    # phase config the dir is preserved so an operator can inspect it.
    await _cleanup_worktree_if_any(task_run, ssh, phase_config)

    # Remove task-scoped workspace directory to free disk space.
    # Only delete if path ends with the task run ID (safety guard against
    # accidentally removing a shared base directory).
    ws_path = task_run.workspace_path
    parts = ws_path.split("/") if ws_path else []
    if ws_path and ws_path.endswith(f"/{task_run.id}") and len(parts) >= 4:
        await broadcaster.log(
            task_run.id, f"Removing task workspace: {ws_path}", phase="finalization"
        )
        await ssh.run_command(f"rm -rf {shlex.quote(ws_path)}", timeout=60)

    await broadcaster.log(task_run.id, "Cleanup complete", phase="finalization")


async def _cleanup_worktree_if_any(task_run: TaskRun, ssh, phase_config: dict | None) -> None:
    """Remove the per-run worktree if workspace_setup created one.

    No-op when:
      * workspace_setup did not record worktree paths (default strategy)
      * phase_config sets ``keep_workspace: true`` (debugging escape hatch)

    Errors are swallowed — finalization should never fail because of a
    cleanup hiccup; the orphan-cleanup scheduler will sweep stragglers.
    """
    worktree_meta = (task_run.workspace_result or {}).get("worktree_paths")
    if not isinstance(worktree_meta, dict):
        return
    keep = bool((phase_config or {}).get("keep_workspace"))
    if keep:
        await broadcaster.log(
            task_run.id,
            f"Keeping worktree {worktree_meta.get('worktree_dir')} for debugging",
            phase="finalization",
        )
        return
    try:
        paths = WorktreePaths(**worktree_meta)
    except TypeError:
        logger.warning(
            "run #%d: worktree_paths metadata has unexpected shape: %r",
            task_run.id,
            worktree_meta,
        )
        return
    try:
        await WorktreeManager(ssh).remove(paths)
        await broadcaster.log(
            task_run.id, f"Removed worktree {paths.worktree_dir}", phase="finalization"
        )
    except Exception as exc:
        logger.warning(
            "run #%d: worktree cleanup failed for %s: %s",
            task_run.id,
            paths.worktree_dir,
            exc,
        )


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
