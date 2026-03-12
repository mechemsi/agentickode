# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Parse git URLs into provider, owner, repo components."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_HOST_TO_PROVIDER: dict[str, str] = {
    "github.com": "github",
    "gitlab.com": "gitlab",
    "bitbucket.org": "bitbucket",
}

# SSH URL pattern: git@host:owner/repo(.git)?
_SSH_RE = re.compile(r"^git@([^:]+):([^/]+)/([^/]+?)(?:\.git)?$")


@dataclass
class ParsedGitUrl:
    provider: str  # "github" | "gitlab" | "gitea" | "bitbucket" | "unknown"
    owner: str
    repo: str
    host: str  # raw hostname


def _provider_from_host(host: str) -> str:
    return _HOST_TO_PROVIDER.get(host, "unknown")


def parse_git_url(url: str) -> ParsedGitUrl:
    """Parse a git URL (SSH or HTTPS/HTTP) into its components.

    Supported formats:
        git@github.com:owner/repo.git
        git@github.com:owner/repo
        https://github.com/owner/repo.git
        https://github.com/owner/repo
        http://github.com/owner/repo

    Raises:
        ValueError: if the URL cannot be parsed into owner/repo parts.
    """
    url = url.strip().rstrip("/")

    # --- SSH format ---
    m = _SSH_RE.match(url)
    if m:
        host, owner, repo = m.group(1), m.group(2), m.group(3)
        if not owner or not repo:
            raise ValueError(f"Could not extract owner/repo from SSH URL: {url!r}")
        return ParsedGitUrl(
            provider=_provider_from_host(host),
            owner=owner,
            repo=repo,
            host=host,
        )

    # --- HTTPS / HTTP format ---
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(
            f"Unsupported URL format (expected git@host:owner/repo or https://host/owner/repo): {url!r}"
        )

    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"Could not determine host from URL: {url!r}")

    # Strip leading slash, strip trailing .git
    path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]

    parts = path.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Could not extract owner/repo from URL path {parsed.path!r} in: {url!r}")

    owner, repo = parts[0], parts[1]
    return ParsedGitUrl(
        provider=_provider_from_host(host),
        owner=owner,
        repo=repo,
        host=host,
    )