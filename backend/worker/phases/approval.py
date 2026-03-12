# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 5: Approval — push branch, create PR.

The pipeline handles parking based on trigger_mode=wait_for_approval
from the PhaseExecution row. Git operations execute on remote via SSH.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps, get_git_provider
from backend.services.git.ops import get_repo_https_url
from backend.services.html_to_text import html_to_text
from backend.services.http_client import get_http_client
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._helpers import get_auth_url, get_project_token, get_ssh_for_run

logger = logging.getLogger("autodev.phases.approval")

PHASE_META = {
    "description": "Push branch and create pull request",
}


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> None:
    """Push branch and create PR. Pipeline handles parking via trigger_mode."""

    review = task_run.review_result or {}

    await broadcaster.log(task_run.id, "Connecting to workspace server", phase="approval")
    ssh = await get_ssh_for_run(task_run, session)
    remote_git = RemoteGitOps(ssh)
    await broadcaster.log(task_run.id, f"Connected to {ssh.hostname}", phase="approval")

    # Check if branch has commits ahead of default branch
    cwd = task_run.workspace_path
    default_branch = str(task_run.default_branch)
    try:
        diff_check = await remote_git.run_git(
            ["log", f"{default_branch}..{task_run.branch_name}", "--oneline"],
            cwd=cwd,
        )
        output = diff_check.stdout.strip() if diff_check.stdout else ""
        commit_count = len(output.splitlines()) if output else 0
    except RuntimeError:
        commit_count = 0
    await broadcaster.log(
        task_run.id,
        f"Branch has {commit_count} commit(s) ahead of {default_branch}",
        phase="approval",
    )
    if commit_count == 0:
        raise RuntimeError(
            f"Branch {task_run.branch_name} has no commits ahead of {default_branch}. "
            "The coding agent may not have made any changes."
        )

    # Resolve per-project token (e.g. Bitbucket repo access token)
    project_token = await get_project_token(task_run, session)

    # Ensure remote has auth credentials, then push
    base_url = get_repo_https_url(task_run.git_provider, task_run.repo_owner, task_run.repo_name)
    auth_url, method = await get_auth_url(
        base_url, task_run.git_provider, ssh, token_override=project_token
    )
    await broadcaster.log(
        task_run.id,
        f"Pushing branch {task_run.branch_name} (auth={method})",
        phase="approval",
    )
    await remote_git.run_git(["remote", "set-url", "origin", auth_url], cwd=cwd)
    await remote_git.run_git(["push", "-u", "origin", task_run.branch_name], cwd=cwd)
    await broadcaster.log(task_run.id, "Branch pushed successfully", phase="approval")

    # Create PR
    pr_body = _build_pr_body(task_run, review)
    repo_path = f"{task_run.repo_owner}/{task_run.repo_name}"

    await broadcaster.log(
        task_run.id,
        f"Creating PR: [AI] {task_run.title} on {task_run.git_provider}",
        phase="approval",
    )

    provider = get_git_provider(
        task_run.git_provider, get_http_client(), access_token=project_token
    )
    pr_url = await provider.create_pr(
        repo_path,
        title=f"[AI] {task_run.title}",
        body=pr_body,
        head=task_run.branch_name,
        base=task_run.default_branch,
    )

    await broadcaster.log(task_run.id, f"PR created: {pr_url}", phase="approval")

    task_run.pr_url = pr_url
    await session.commit()

    await broadcaster.event(task_run.id, "approval_requested", {"pr_url": pr_url})


def _build_pr_body(task_run: TaskRun, review: dict) -> str:
    issues = review.get("issues", [])
    suggestions = review.get("suggestions", [])
    approved = review.get("approved", False)
    suggestion_lines = "\n".join(f"- {s}" for s in suggestions) if suggestions else "None"

    return f"""## AI-Generated Pull Request

### Task
{task_run.title}

### Description
{html_to_text(task_run.description)}

### Review Summary
- **Automated Review**: {'Passed' if approved else 'Needs attention'}
- **Issues Found**: {len(issues)}
- **Suggestions**: {len(suggestions)}

### Suggestions from AI Reviewer
{suggestion_lines}

---
*This PR was created automatically by the AI Development Infrastructure.*
*Please review carefully before merging.*
"""