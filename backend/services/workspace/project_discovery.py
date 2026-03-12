# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Discover git projects on a remote workspace server."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from backend.services.workspace.ssh_service import SSHService

SSH_REMOTE_RE = re.compile(r"(?:https?://[^/]+/|git@[^:]+:)(?P<owner>[^/]+)/(?P<name>[^/.\s]+)")

# Map known hostnames to git provider names
_HOST_TO_PROVIDER: dict[str, str] = {
    "github.com": "github",
    "gitlab.com": "gitlab",
    "bitbucket.org": "bitbucket",
}


@dataclass
class DiscoveredProject:
    path: str
    remote_url: str
    owner: str
    name: str
    git_provider: str


class ProjectDiscoveryService:
    """Scan a remote workspace directory for git repositories."""

    def __init__(self, ssh: SSHService):
        self._ssh = ssh

    async def scan_workspace(self, workspace_root: str) -> list[DiscoveredProject]:
        stdout, _, exit_code = await self._ssh.run_command(
            f"find {workspace_root} -maxdepth 2 -name .git -type d 2>/dev/null",
            timeout=30,
        )
        if exit_code != 0 or not stdout.strip():
            return []

        projects: list[DiscoveredProject] = []
        for git_dir in stdout.strip().split("\n"):
            repo_dir = git_dir.removesuffix("/.git")
            remote_url = await self._get_remote(repo_dir)
            if not remote_url:
                continue
            parsed = parse_git_remote(remote_url)
            if parsed:
                owner, name, provider = parsed
                projects.append(
                    DiscoveredProject(
                        path=repo_dir,
                        remote_url=remote_url,
                        owner=owner,
                        name=name,
                        git_provider=provider,
                    )
                )
        return projects

    async def _get_remote(self, repo_dir: str) -> str | None:
        stdout, _, exit_code = await self._ssh.run_command(
            f"git -C {repo_dir} remote get-url origin 2>/dev/null",
            timeout=10,
        )
        if exit_code == 0 and stdout.strip():
            return stdout.strip()
        return None


def detect_provider(url: str) -> str:
    """Detect git provider from a remote URL. Returns 'gitea' as default for self-hosted."""
    url_lower = url.lower()
    # SSH format: git@github.com:owner/repo
    if url_lower.startswith("git@"):
        host = url_lower.split("@", 1)[1].split(":", 1)[0]
    else:
        host = urlparse(url_lower).hostname or ""

    return _HOST_TO_PROVIDER.get(host, "gitea")


def parse_git_remote(url: str) -> tuple[str, str, str] | None:
    """Parse a git remote URL into (owner, name, provider). Handles HTTPS and SSH formats."""
    raw = url
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    match = SSH_REMOTE_RE.search(url)
    if match:
        return match.group("owner"), match.group("name"), detect_provider(raw)
    return None