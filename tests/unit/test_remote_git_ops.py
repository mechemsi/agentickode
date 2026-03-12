# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for RemoteGitOps service."""

from unittest.mock import AsyncMock

import pytest

from backend.services.git import RemoteGitError, RemoteGitOps


@pytest.fixture()
def mock_ssh():
    ssh = AsyncMock()
    ssh.hostname = "10.10.50.25"
    ssh.port = 22
    return ssh


@pytest.fixture()
def remote_git(mock_ssh):
    return RemoteGitOps(mock_ssh)


class TestRunGit:
    async def test_success(self, remote_git, mock_ssh):
        mock_ssh.run_command.return_value = ("ok\n", "", 0)
        result = await remote_git.run_git(["status"], cwd="/workspaces/proj")
        assert result.stdout == "ok\n"
        mock_ssh.run_command.assert_called_once()
        cmd = mock_ssh.run_command.call_args[0][0]
        assert "cd /workspaces/proj && git status" in cmd

    async def test_failure_raises(self, remote_git, mock_ssh):
        mock_ssh.run_command.return_value = ("", "fatal: not a repo", 128)
        with pytest.raises(RemoteGitError, match="not a repo"):
            await remote_git.run_git(["status"], cwd="/workspaces/proj")

    async def test_args_are_quoted(self, remote_git, mock_ssh):
        mock_ssh.run_command.return_value = ("", "", 0)
        await remote_git.run_git(["commit", "-m", "hello world"], cwd="/workspaces/proj")
        cmd = mock_ssh.run_command.call_args[0][0]
        # shlex.quote wraps strings with spaces in quotes
        assert "hello world" in cmd
        assert "git commit -m" in cmd


class TestCloneOrPull:
    async def test_clone_when_no_git_dir(self, remote_git, mock_ssh):
        # test -d returns 1 (not found)
        mock_ssh.run_command.side_effect = [
            ("", "", 0),  # safe.directory
            ("", "", 1),  # test -d
            ("", "", 0),  # mkdir -p
            ("", "", 0),  # git clone
        ]
        await remote_git.clone_or_pull("https://example.com/repo.git", "/workspaces/proj")
        clone_cmd = mock_ssh.run_command.call_args_list[3][0][0]
        assert "git clone" in clone_cmd

    async def test_pull_when_git_dir_exists(self, remote_git, mock_ssh):
        # test -d returns 0 (found)
        mock_ssh.run_command.side_effect = [
            ("", "", 0),  # safe.directory (clone_or_pull)
            ("", "", 0),  # test -d
            ("", "", 0),  # safe.directory (pull)
            ("", "", 0),  # rm -f index.lock
            ("", "", 0),  # git clean -fd
            ("", "", 0),  # git reset --hard HEAD
            ("", "", 0),  # fetch
            ("", "", 0),  # checkout
            ("", "", 0),  # reset --hard origin/main
        ]
        await remote_git.clone_or_pull("https://example.com/repo.git", "/workspaces/proj")
        assert mock_ssh.run_command.call_count == 9

    async def test_clone_failure_raises(self, remote_git, mock_ssh):
        mock_ssh.run_command.side_effect = [
            ("", "", 0),  # safe.directory
            ("", "", 1),  # test -d
            ("", "", 0),  # mkdir -p
            ("", "fatal: repo not found", 128),  # git clone fails
        ]
        with pytest.raises(RemoteGitError, match="git clone.*failed"):
            await remote_git.clone_or_pull("https://example.com/repo.git", "/workspaces/proj")


class TestMkdir:
    async def test_mkdir_success(self, remote_git, mock_ssh):
        mock_ssh.run_command.return_value = ("", "", 0)
        await remote_git.mkdir("/workspaces/new-dir")
        cmd = mock_ssh.run_command.call_args[0][0]
        assert "mkdir -p" in cmd
        assert "/workspaces/new-dir" in cmd

    async def test_mkdir_failure_raises(self, remote_git, mock_ssh):
        mock_ssh.run_command.return_value = ("", "Permission denied", 1)
        with pytest.raises(RemoteGitError, match="mkdir -p.*failed"):
            await remote_git.mkdir("/root/forbidden")