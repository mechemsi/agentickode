# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Git credential helpers — pure string manipulation, no I/O.

NOTE: run_git() and clone_or_pull() have been removed. Use RemoteGitOps instead.
"""

from __future__ import annotations

from urllib.parse import urlparse

from backend.config import settings


def inject_git_credentials(
    repo_url: str, git_provider: str = "gitea", token_override: str | None = None
) -> str:
    """Inject auth token into repo URL for authenticated clone/push.

    When *token_override* is provided it is used instead of the global token
    from settings (useful for per-project / per-repo scoped tokens).
    """
    if not repo_url.startswith("https://"):
        return repo_url

    if git_provider == "github":
        token = token_override or settings.github_token
        if not token:
            return repo_url
        return repo_url.replace("https://", f"https://x-access-token:{token}@", 1)

    if git_provider == "bitbucket":
        token = token_override or settings.bitbucket_access_token
        if not token:
            return repo_url
        return repo_url.replace("https://", f"https://x-token-auth:{token}@", 1)

    if git_provider == "gitlab":
        token = token_override or settings.gitlab_token
        if not token:
            return repo_url
        return repo_url.replace("https://", f"https://oauth2:{token}@", 1)

    # gitea (default)
    token = token_override or settings.gitea_token
    if not token:
        return repo_url
    return repo_url.replace("https://", f"https://ai-agent:{token}@", 1)


def get_repo_https_url(git_provider: str, owner: str, name: str) -> str:
    """Build the HTTPS clone URL for a repo given the git provider."""
    if git_provider == "github":
        return f"https://github.com/{owner}/{name}.git"
    if git_provider == "bitbucket":
        return f"https://bitbucket.org/{owner}/{name}.git"
    if git_provider == "gitlab":
        base = settings.gitlab_api_url.rstrip("/")
        return f"{base}/{owner}/{name}.git"
    # gitea (default)
    base = settings.gitea_url.rstrip("/")
    return f"{base}/{owner}/{name}.git"


def to_ssh_url(repo_url: str) -> str | None:
    """Convert an HTTPS repo URL to git-over-SSH format.

    Returns None if the URL is not HTTPS or cannot be converted.

    Examples:
        https://github.com/org/repo.git → git@github.com:org/repo.git
        https://gitea.local/org/repo.git → git@gitea.local:org/repo.git
    """
    if not repo_url.startswith("https://"):
        return None
    parsed = urlparse(repo_url)
    if not parsed.hostname:
        return None
    path = parsed.path.lstrip("/")
    if not path:
        return None
    return f"git@{parsed.hostname}:{path}"
