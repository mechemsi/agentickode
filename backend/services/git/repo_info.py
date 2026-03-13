# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Query git provider APIs to retrieve repository metadata."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import httpx

from backend.config import settings

if TYPE_CHECKING:
    from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.repo_info")


async def get_default_branch(
    provider: str,
    owner: str,
    repo: str,
    client: httpx.AsyncClient,
) -> str:
    """Query the provider API to get the repo's default branch.

    Raises:
        httpx.HTTPStatusError: if the API returns a non-2xx response.
        ValueError: if the provider is unknown or the response is malformed.
    """
    timeout = httpx.Timeout(10.0)

    if provider == "github":
        url = f"{settings.github_api_url}/repos/{owner}/{repo}"
        headers = {"Authorization": f"Bearer {settings.github_token}"}
        response = await client.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return str(response.json()["default_branch"])

    if provider == "gitlab":
        encoded = f"{owner}%2F{repo}"
        url = f"{settings.gitlab_api_url}/api/v4/projects/{encoded}"
        headers = {"PRIVATE-TOKEN": settings.gitlab_token}
        response = await client.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return str(response.json()["default_branch"])

    if provider == "gitea":
        url = f"{settings.gitea_url}/api/v1/repos/{owner}/{repo}"
        headers = {"Authorization": f"token {settings.gitea_token}"}
        response = await client.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return str(response.json()["default_branch"])

    if provider == "bitbucket":
        url = f"{settings.bitbucket_base_url}/2.0/repositories/{owner}/{repo}"
        headers = {"Authorization": f"Bearer {settings.bitbucket_access_token}"}
        response = await client.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return str(data["mainbranch"]["name"])

    raise ValueError(f"Cannot detect branch for unknown provider: {provider!r}")


async def get_default_branch_via_ssh(
    ssh: SSHService,
    git_url: str,
) -> str:
    """Detect the default branch by running ``git ls-remote`` on a workspace server.

    Uses ``--symref`` to read the symbolic ref for HEAD, which reveals the
    default branch name without cloning.

    Raises:
        RuntimeError: if the command fails or the output cannot be parsed.
    """
    stdout, stderr, rc = await ssh.run_command(
        f"git ls-remote --symref {git_url} HEAD",
        timeout=15,
    )
    if rc != 0:
        error = stderr.strip() or stdout.strip() or f"exit code {rc}"
        raise RuntimeError(f"git ls-remote failed: {error}")

    # Parse output like: "ref: refs/heads/main\tHEAD"
    match = re.search(r"ref:\s+refs/heads/(\S+)\s+HEAD", stdout)
    if match:
        return match.group(1)

    # Fallback: if --symref output is missing (old git), just return "main"
    logger.warning("Could not parse default branch from ls-remote output, defaulting to 'main'")
    return "main"
