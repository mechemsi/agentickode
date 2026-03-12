# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for GitAccessService."""

from unittest.mock import AsyncMock

import pytest

from backend.services.git import GitAccessService
from backend.services.git.access_service import _parse_ssh_output


class TestParseSshOutput:
    def test_github_success(self):
        output = "Hi octocat! You've successfully authenticated, but GitHub does not provide shell access."
        result = _parse_ssh_output("github.com", "GitHub", output)
        assert result.connected is True
        assert result.username == "octocat"

    def test_gitlab_success(self):
        output = "Welcome to GitLab, @john_doe!"
        result = _parse_ssh_output("gitlab.com", "GitLab", output)
        assert result.connected is True
        assert result.username == "john_doe"

    def test_bitbucket_success(self):
        output = "logged in as myuser.\nYou can use git to connect to Bitbucket."
        result = _parse_ssh_output("bitbucket.org", "Bitbucket", output)
        assert result.connected is True
        assert result.username == "myuser."

    def test_permission_denied(self):
        output = "git@github.com: Permission denied (publickey)."
        result = _parse_ssh_output("github.com", "GitHub", output)
        assert result.connected is False
        assert result.error is not None

    def test_empty_output(self):
        result = _parse_ssh_output("github.com", "GitHub", "")
        assert result.connected is False
        assert result.error == "No response"

    def test_generic_success(self):
        output = "Welcome to our self-hosted git server"
        result = _parse_ssh_output("git.example.com", "Example", output)
        assert result.connected is True


class TestGetPublicKey:
    @pytest.fixture
    def ssh_mock(self):
        return AsyncMock()

    async def test_ed25519_key_found(self, ssh_mock):
        ssh_mock.run_command = AsyncMock(return_value=("ssh-ed25519 AAAA... user@host", "", 0))
        svc = GitAccessService(ssh_mock)
        result = await svc.get_public_key()
        assert result.has_key is True
        assert result.key_type == "ed25519"
        assert result.public_key == "ssh-ed25519 AAAA... user@host"

    async def test_rsa_fallback(self, ssh_mock):
        # ed25519 not found, rsa found
        ssh_mock.run_command = AsyncMock(
            side_effect=[
                ("", "", 1),  # ed25519 fails
                ("ssh-rsa BBBB... user@host", "", 0),  # rsa succeeds
            ]
        )
        svc = GitAccessService(ssh_mock)
        result = await svc.get_public_key()
        assert result.has_key is True
        assert result.key_type == "rsa"

    async def test_no_key(self, ssh_mock):
        ssh_mock.run_command = AsyncMock(return_value=("", "", 1))
        svc = GitAccessService(ssh_mock)
        result = await svc.get_public_key()
        assert result.has_key is False
        assert result.public_key is None


class TestGenerateKey:
    async def test_existing_key_not_forced(self):
        ssh = AsyncMock()
        ssh.run_command = AsyncMock(return_value=("ssh-ed25519 AAAA... user@host", "", 0))
        svc = GitAccessService(ssh)
        result = await svc.generate_key("test-server")
        assert result.has_key is True
        # Should not have called ssh-keygen
        calls = [c[0][0] for c in ssh.run_command.call_args_list]
        assert not any("ssh-keygen" in c for c in calls)

    async def test_generate_new_key(self):
        ssh = AsyncMock()
        ssh.run_command = AsyncMock(
            side_effect=[
                ("", "", 1),  # no ed25519
                ("", "", 1),  # no rsa
                ("", "", 0),  # ssh-keygen success
                ("", "", 0),  # ssh-keyscan known_hosts
                ("ssh-ed25519 NEW... autodev@srv", "", 0),  # read new key
            ]
        )
        svc = GitAccessService(ssh)
        result = await svc.generate_key("srv")
        assert result.has_key is True
        assert result.public_key == "ssh-ed25519 NEW... autodev@srv"


class TestCheckAll:
    async def test_no_key_skips_providers(self):
        ssh = AsyncMock()
        ssh.run_command = AsyncMock(return_value=("", "", 1))
        svc = GitAccessService(ssh)
        key_info, providers = await svc.check_all()
        assert key_info.has_key is False
        assert len(providers) == 3  # default providers
        assert all(not p.connected for p in providers)
        assert all(p.error == "No SSH key found" for p in providers)