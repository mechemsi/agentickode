# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Git services subpackage — barrel re-exports for backward compatibility."""

from backend.services.git.access_service import (
    DEFAULT_PROVIDERS,
    GitAccessService,
    KeyInfo,
    ProviderStatus,
)
from backend.services.git.bitbucket import BitbucketProvider
from backend.services.git.gitea import GiteaProvider
from backend.services.git.github import GitHubProvider
from backend.services.git.gitlab import GitLabProvider
from backend.services.git.ops import inject_git_credentials, to_ssh_url
from backend.services.git.protocol import GitProvider, get_git_provider
from backend.services.git.remote_ops import GitResult, RemoteGitError, RemoteGitOps

__all__ = [
    "DEFAULT_PROVIDERS",
    "BitbucketProvider",
    "GitAccessService",
    "GitHubProvider",
    "GitLabProvider",
    "GitProvider",
    "GitResult",
    "GiteaProvider",
    "KeyInfo",
    "ProviderStatus",
    "RemoteGitError",
    "RemoteGitOps",
    "get_git_provider",
    "inject_git_credentials",
    "to_ssh_url",
]