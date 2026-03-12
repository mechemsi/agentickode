# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase: PR Fetch — fetch PR diff and comments via git provider API.

Used by the pr-review workflow. No SSH/workspace needed.
"""

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import get_git_provider
from backend.services.http_client import get_http_client
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._helpers import get_project_token

logger = logging.getLogger("autodev.phases.pr_fetch")

PHASE_META = {
    "description": "Fetch PR diff and comments from git provider",
}

# Patterns to extract owner/repo and PR number from common PR URLs
_PR_URL_PATTERNS = [
    re.compile(r"https?://[^/]+/([^/]+/[^/]+)/pulls?/(\d+)"),  # Gitea / GitHub
]


def _parse_pr_url(url: str) -> tuple[str, int]:
    """Extract repo_path and pr_number from a PR URL."""
    for pattern in _PR_URL_PATTERNS:
        m = pattern.search(url)
        if m:
            return m.group(1), int(m.group(2))
    raise ValueError(f"Could not parse PR URL: {url}")


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> dict:
    """Fetch PR diff and comments from git provider API."""
    meta = task_run.task_source_meta or {}
    pr_url = meta.get("pr_url", "")
    pr_number = meta.get("pr_number")
    repo_path = f"{task_run.repo_owner}/{task_run.repo_name}"

    if pr_url and not pr_number:
        repo_path, pr_number = _parse_pr_url(pr_url)
    elif not pr_number:
        raise ValueError("No pr_url or pr_number in task_source_meta")

    await broadcaster.log(
        task_run.id,
        f"Fetching PR #{pr_number} from {repo_path} via {task_run.git_provider}",
        phase="pr_fetch",
    )

    project_token = await get_project_token(task_run, session)
    client = get_http_client()
    provider = get_git_provider(task_run.git_provider, client, access_token=project_token)

    diff = await provider.get_pr_diff(repo_path, int(pr_number))
    comments = await provider.get_pr_comments(repo_path, int(pr_number))

    result = {
        "pr_diff": diff[:50000],  # Limit diff size
        "pr_comments": comments[:50],  # Limit comment count
        "pr_number": pr_number,
        "repo_path": repo_path,
    }

    task_run.coding_results = {**(task_run.coding_results or {}), **result}
    await session.commit()

    await broadcaster.log(
        task_run.id,
        f"Fetched PR diff ({len(diff)} chars) and {len(comments)} comments",
        phase="pr_fetch",
    )
    return result