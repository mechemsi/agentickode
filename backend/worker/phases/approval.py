# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 5: Approval — push branch, create PR.

The pipeline handles parking based on trigger_mode=wait_for_approval
from the PhaseExecution row. Git operations execute on remote via SSH.
"""

import logging
import shlex

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps, get_git_provider
from backend.services.git.ops import get_repo_https_url
from backend.services.html_to_text import html_to_text
from backend.services.http_client import get_http_client
from backend.services.workspace.ssh_service import SSHService
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._helpers import get_auth_url, get_project_token, get_ssh_for_run

logger = logging.getLogger("agentickode.phases.approval")

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

    # Create PR — try gh CLI first (works for contributor repos), fall back to API
    pr_body = _build_pr_body(task_run, review)
    repo_path = f"{task_run.repo_owner}/{task_run.repo_name}"
    pr_title = f"[AI] {task_run.title}"

    await broadcaster.log(
        task_run.id,
        f"Creating PR: {pr_title} on {task_run.git_provider}",
        phase="approval",
    )

    pr_url: str | None = None
    if task_run.git_provider == "github":
        pr_url = await _try_gh_pr_create(ssh, cwd, pr_title, pr_body, task_run)

    if not pr_url:
        provider = get_git_provider(
            task_run.git_provider, get_http_client(), access_token=project_token
        )
        pr_url = await provider.create_pr(
            repo_path,
            title=pr_title,
            body=pr_body,
            head=task_run.branch_name,
            base=task_run.default_branch,
        )

    await broadcaster.log(task_run.id, f"PR created: {pr_url}", phase="approval")

    task_run.pr_url = pr_url
    await session.commit()

    await broadcaster.event(task_run.id, "approval_requested", {"pr_url": pr_url})


async def _try_gh_pr_create(
    ssh: SSHService,
    cwd: str,
    title: str,
    body: str,
    task_run: TaskRun,
) -> str | None:
    """Try creating PR via gh CLI on the workspace server. Returns PR URL or None."""
    try:
        # Check if gh is available
        _, _, rc = await ssh.run_command("command -v gh", timeout=10)
        if rc != 0:
            return None

        await broadcaster.log(task_run.id, "Using gh CLI for PR creation", phase="approval")

        # Run as worker user with env sourced (GITHUB_TOKEN lives in .agentickode_env)
        gh_cmd = (
            f"cd {shlex.quote(cwd)} && "
            f"gh pr create"
            f" --title {shlex.quote(title)}"
            f" --body {shlex.quote(body)}"
            f" --base {shlex.quote(str(task_run.default_branch))}"
            f" --head {shlex.quote(task_run.branch_name)}"
        )
        # Source env for GITHUB_TOKEN, then run gh
        inner = f". ~/.agentickode_env 2>/dev/null; {gh_cmd}"
        # Try as worker user first (has token in env), fall back to root
        for user_wrap in [
            f"runuser -l coder -c {shlex.quote(inner)}",
            inner,
        ]:
            stdout, stderr, rc = await ssh.run_command(user_wrap, timeout=30)
            if rc == 0 and stdout.strip():
                pr_url = stdout.strip().splitlines()[-1]
                if pr_url.startswith("http"):
                    return pr_url
        logger.info("gh pr create failed (rc=%d): %s", rc, stderr.strip()[:300])
    except Exception:
        logger.debug("gh pr create unavailable, falling back to API", exc_info=True)
    return None


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
