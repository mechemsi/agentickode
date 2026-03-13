# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for git_ops helpers.

run_git and clone_or_pull have been moved to RemoteGitOps.
See test_remote_git_ops.py for those tests.
"""

from unittest.mock import patch

from backend.services.git import inject_git_credentials, to_ssh_url
from backend.services.git.ops import get_repo_https_url


class TestInjectGitCredentials:
    def test_gitea_injects_token(self):
        with patch("backend.services.git.ops.settings") as s:
            s.gitea_token = "test-token"
            result = inject_git_credentials("https://gitea.test/org/repo.git", "gitea")
            assert "ai-agent:test-token@" in result

    def test_github_injects_token(self):
        with patch("backend.services.git.ops.settings") as s:
            s.github_token = "ghp_tok"
            result = inject_git_credentials("https://github.com/org/repo.git", "github")
            assert "x-access-token:ghp_tok@" in result

    def test_no_token_returns_unchanged(self):
        with patch("backend.services.git.ops.settings") as s:
            s.gitea_token = ""
            result = inject_git_credentials("https://gitea.test/org/repo.git", "gitea")
            assert result == "https://gitea.test/org/repo.git"

    def test_bitbucket_injects_credentials(self):
        with patch("backend.services.git.ops.settings") as s:
            s.bitbucket_access_token = "access-token-123"
            result = inject_git_credentials("https://bitbucket.org/ws/repo.git", "bitbucket")
            assert "x-token-auth:access-token-123@" in result

    def test_bitbucket_no_credentials_returns_unchanged(self):
        with patch("backend.services.git.ops.settings") as s:
            s.bitbucket_access_token = ""
            result = inject_git_credentials("https://bitbucket.org/ws/repo.git", "bitbucket")
            assert result == "https://bitbucket.org/ws/repo.git"

    def test_gitlab_injects_token(self):
        with patch("backend.services.git.ops.settings") as s:
            s.gitlab_token = "glpat-abc123"
            result = inject_git_credentials("https://gitlab.com/org/repo.git", "gitlab")
            assert "oauth2:glpat-abc123@" in result

    def test_ssh_url_returns_unchanged(self):
        result = inject_git_credentials("git@github.com:org/repo.git", "github")
        assert result == "git@github.com:org/repo.git"


class TestGetRepoHttpsUrl:
    def test_github(self):
        result = get_repo_https_url("github", "org", "repo")
        assert result == "https://github.com/org/repo.git"

    def test_bitbucket(self):
        result = get_repo_https_url("bitbucket", "workspace", "repo")
        assert result == "https://bitbucket.org/workspace/repo.git"

    def test_gitlab(self):
        with patch("backend.services.git.ops.settings") as s:
            s.gitlab_api_url = "https://gitlab.com"
            result = get_repo_https_url("gitlab", "org", "repo")
            assert result == "https://gitlab.com/org/repo.git"

    def test_gitea(self):
        with patch("backend.services.git.ops.settings") as s:
            s.gitea_url = "https://gitea.local"
            result = get_repo_https_url("gitea", "org", "repo")
            assert result == "https://gitea.local/org/repo.git"


class TestToSshUrl:
    def test_github_https_to_ssh(self):
        result = to_ssh_url("https://github.com/org/repo.git")
        assert result == "git@github.com:org/repo.git"

    def test_gitea_https_to_ssh(self):
        result = to_ssh_url("https://gitea.local/myorg/myrepo.git")
        assert result == "git@gitea.local:myorg/myrepo.git"

    def test_non_https_returns_none(self):
        assert to_ssh_url("git@github.com:org/repo.git") is None

    def test_http_returns_none(self):
        assert to_ssh_url("http://github.com/org/repo.git") is None

    def test_empty_path_returns_none(self):
        assert to_ssh_url("https://github.com") is None
        assert to_ssh_url("https://github.com/") is None

    def test_preserves_path_with_no_git_suffix(self):
        result = to_ssh_url("https://github.com/org/repo")
        assert result == "git@github.com:org/repo"
