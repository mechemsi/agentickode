# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""GitProvider Protocol and factory function."""

import logging
from typing import Protocol

import httpx

logger = logging.getLogger("autodev.git_provider")


class GitProvider(Protocol):
    """Interface for git hosting operations (Gitea, GitHub, etc.)."""

    async def create_repo(self, owner: str, name: str) -> bool: ...
    async def create_pr(
        self, repo_path: str, title: str, body: str, head: str, base: str
    ) -> str: ...
    async def merge_pr(self, pr_url: str) -> bool: ...
    async def get_pr_diff(self, repo_path: str, pr_number: int) -> str: ...
    async def get_pr_comments(self, repo_path: str, pr_number: int) -> list[dict]: ...
    async def post_pr_comment(self, repo_path: str, pr_number: int, body: str) -> None: ...
    async def list_issues(
        self, repo_path: str, state: str = "open", limit: int = 30
    ) -> list[dict]: ...


def get_git_provider(
    provider_name: str,
    client: httpx.AsyncClient,
    access_token: str | None = None,
) -> GitProvider:
    """Factory function returning the appropriate GitProvider implementation.

    When *access_token* is provided it overrides the global token from settings
    (useful for per-project / per-repo scoped tokens, e.g. Bitbucket repo tokens).
    """
    from backend.services.git.bitbucket import BitbucketProvider
    from backend.services.git.gitea import GiteaProvider
    from backend.services.git.github import GitHubProvider
    from backend.services.git.gitlab import GitLabProvider

    if provider_name == "github":
        return (
            GitHubProvider(client, token=access_token) if access_token else GitHubProvider(client)
        )
    if provider_name == "bitbucket":
        return (
            BitbucketProvider(client, access_token=access_token)
            if access_token
            else BitbucketProvider(client)
        )
    if provider_name == "gitlab":
        return (
            GitLabProvider(client, token=access_token) if access_token else GitLabProvider(client)
        )
    return GiteaProvider(client, token=access_token) if access_token else GiteaProvider(client)