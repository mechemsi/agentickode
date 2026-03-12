# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for ProjectDiscoveryService, parse_git_remote, and detect_provider."""

from unittest.mock import AsyncMock

import pytest

from backend.services.workspace.project_discovery import (
    ProjectDiscoveryService,
    detect_provider,
    parse_git_remote,
)


class TestDetectProvider:
    def test_github_https(self):
        assert detect_provider("https://github.com/owner/repo.git") == "github"

    def test_github_ssh(self):
        assert detect_provider("git@github.com:owner/repo.git") == "github"

    def test_gitlab_https(self):
        assert detect_provider("https://gitlab.com/owner/repo.git") == "gitlab"

    def test_gitlab_ssh(self):
        assert detect_provider("git@gitlab.com:owner/repo.git") == "gitlab"

    def test_bitbucket_https(self):
        assert detect_provider("https://bitbucket.org/owner/repo.git") == "bitbucket"

    def test_bitbucket_ssh(self):
        assert detect_provider("git@bitbucket.org:owner/repo.git") == "bitbucket"

    def test_gitea_self_hosted(self):
        assert detect_provider("https://gitea.example.com/owner/repo.git") == "gitea"

    def test_gitea_ssh_self_hosted(self):
        assert detect_provider("git@gitea.local:owner/repo.git") == "gitea"

    def test_unknown_host_defaults_to_gitea(self):
        assert detect_provider("https://myserver.internal/owner/repo.git") == "gitea"

    def test_case_insensitive(self):
        assert detect_provider("https://GitHub.COM/owner/repo.git") == "github"


class TestParseGitRemote:
    def test_https_github(self):
        result = parse_git_remote("https://github.com/owner/repo.git")
        assert result == ("owner", "repo", "github")

    def test_https_no_dot_git(self):
        result = parse_git_remote("https://github.com/owner/repo")
        assert result == ("owner", "repo", "github")

    def test_ssh_github(self):
        result = parse_git_remote("git@github.com:owner/repo.git")
        assert result == ("owner", "repo", "github")

    def test_ssh_no_dot_git(self):
        result = parse_git_remote("git@github.com:owner/repo")
        assert result == ("owner", "repo", "github")

    def test_gitea_https(self):
        result = parse_git_remote("https://gitea.example.com/myorg/myrepo.git")
        assert result == ("myorg", "myrepo", "gitea")

    def test_gitlab_ssh(self):
        result = parse_git_remote("git@gitlab.com:team/project.git")
        assert result == ("team", "project", "gitlab")

    def test_bitbucket_https(self):
        result = parse_git_remote("https://bitbucket.org/company/app.git")
        assert result == ("company", "app", "bitbucket")

    def test_trailing_slash(self):
        result = parse_git_remote("https://github.com/owner/repo/")
        assert result == ("owner", "repo", "github")

    def test_whitespace(self):
        result = parse_git_remote("  https://github.com/owner/repo.git  \n")
        assert result == ("owner", "repo", "github")

    def test_invalid_url_returns_none(self):
        assert parse_git_remote("not-a-url") is None

    def test_empty_string_returns_none(self):
        assert parse_git_remote("") is None


@pytest.fixture
def mock_ssh():
    return AsyncMock()


class TestScanWorkspace:
    async def test_finds_repos_with_providers(self, mock_ssh: AsyncMock):
        async def run_command(cmd: str, timeout: int = 30):
            if cmd.startswith("find"):
                return ("/workspaces/project-a/.git\n/workspaces/project-b/.git\n", "", 0)
            if "project-a" in cmd:
                return ("https://github.com/org/project-a.git\n", "", 0)
            if "project-b" in cmd:
                return ("git@gitea.local:team/project-b.git\n", "", 0)
            return ("", "", 1)

        mock_ssh.run_command = AsyncMock(side_effect=run_command)
        svc = ProjectDiscoveryService(mock_ssh)
        projects = await svc.scan_workspace("/workspaces")

        assert len(projects) == 2
        assert projects[0].owner == "org"
        assert projects[0].name == "project-a"
        assert projects[0].git_provider == "github"
        assert projects[1].owner == "team"
        assert projects[1].name == "project-b"
        assert projects[1].git_provider == "gitea"

    async def test_gitlab_detected(self, mock_ssh: AsyncMock):
        async def run_command(cmd: str, timeout: int = 30):
            if cmd.startswith("find"):
                return ("/workspaces/proj/.git\n", "", 0)
            if "remote get-url" in cmd:
                return ("git@gitlab.com:myteam/myapp.git\n", "", 0)
            return ("", "", 1)

        mock_ssh.run_command = AsyncMock(side_effect=run_command)
        svc = ProjectDiscoveryService(mock_ssh)
        projects = await svc.scan_workspace("/workspaces")

        assert len(projects) == 1
        assert projects[0].git_provider == "gitlab"

    async def test_empty_workspace(self, mock_ssh: AsyncMock):
        mock_ssh.run_command = AsyncMock(return_value=("", "", 0))
        svc = ProjectDiscoveryService(mock_ssh)
        projects = await svc.scan_workspace("/workspaces")
        assert projects == []

    async def test_find_fails(self, mock_ssh: AsyncMock):
        mock_ssh.run_command = AsyncMock(return_value=("", "error", 1))
        svc = ProjectDiscoveryService(mock_ssh)
        projects = await svc.scan_workspace("/workspaces")
        assert projects == []

    async def test_skips_repos_without_remote(self, mock_ssh: AsyncMock):
        async def run_command(cmd: str, timeout: int = 30):
            if cmd.startswith("find"):
                return ("/workspaces/local-only/.git\n", "", 0)
            if "remote get-url" in cmd:
                return ("", "fatal: no remote", 1)
            return ("", "", 1)

        mock_ssh.run_command = AsyncMock(side_effect=run_command)
        svc = ProjectDiscoveryService(mock_ssh)
        projects = await svc.scan_workspace("/workspaces")
        assert projects == []