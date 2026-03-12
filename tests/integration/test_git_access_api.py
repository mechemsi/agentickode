# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for git access API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from backend.services.workspace.ssh_service import SSHTestResult as SSHTestResultData


@pytest.fixture
def mock_ssh_for_git():
    """Mock SSH for git access tests — server creation + git access calls."""
    with patch("backend.api.servers.workspace_servers.SSHService") as ws_mock_cls:
        ws_instance = AsyncMock()
        ws_mock_cls.return_value = ws_instance
        ws_mock_cls.for_server = lambda server: ws_instance
        ws_instance.test_connection = AsyncMock(
            return_value=SSHTestResultData(success=True, latency_ms=5.0)
        )

        with (
            patch("backend.api.servers.workspace_servers.AgentDiscoveryService") as mock_agent_cls,
            patch("backend.api.servers.workspace_servers.ProjectDiscoveryService") as mock_proj_cls,
            patch("backend.api.servers.git_access.SSHService") as ga_mock_cls,
        ):
            mock_agent_cls.return_value.discover_all = AsyncMock(return_value=[])
            mock_proj_cls.return_value.scan_workspace = AsyncMock(return_value=[])

            ga_instance = AsyncMock()
            ga_mock_cls.for_server = lambda server: ga_instance
            # Default: has key, github connected
            ga_instance.run_command = AsyncMock(
                return_value=("ssh-ed25519 AAAA... autodev@test", "", 0)
            )

            yield ga_instance


class TestCheckGitAccess:
    async def test_check_returns_key_and_providers(self, client: AsyncClient, mock_ssh_for_git):
        # Create a server first
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "git-test-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]

        # Mock the git access service calls
        mock_ssh_for_git.run_command = AsyncMock(
            side_effect=[
                ("ssh-ed25519 AAAA... autodev@test", "", 0),  # get_public_key ed25519
                (
                    "Hi octocat! You've successfully authenticated, but GitHub does not provide shell access.",
                    "",
                    1,
                ),  # github
                ("Welcome to GitLab, @user!", "", 1),  # gitlab
                (
                    "git@bitbucket.org: Permission denied (publickey).",
                    "",
                    1,
                ),  # bitbucket
            ]
        )

        resp = await client.post(f"/api/workspace-servers/{server_id}/git-access/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_key"] is True
        assert data["public_key"] is not None
        assert data["key_type"] == "ed25519"
        assert len(data["providers"]) == 3

    async def test_check_not_found(self, client: AsyncClient, mock_ssh_for_git):
        resp = await client.post("/api/workspace-servers/999/git-access/check")
        assert resp.status_code == 404

    async def test_check_no_key(self, client: AsyncClient, mock_ssh_for_git):
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "nokey-srv", "hostname": "10.0.0.2"},
        )
        server_id = create_resp.json()["id"]

        # No key found
        mock_ssh_for_git.run_command = AsyncMock(return_value=("", "", 1))

        resp = await client.post(f"/api/workspace-servers/{server_id}/git-access/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_key"] is False
        assert all(not p["connected"] for p in data["providers"])


class TestGenerateGitKey:
    async def test_generate_key(self, client: AsyncClient, mock_ssh_for_git):
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "keygen-srv", "hostname": "10.0.0.3"},
        )
        server_id = create_resp.json()["id"]

        # No existing key, then keygen succeeds, keyscan, then read new key
        # Server creation defaults worker_user="coder", so generate_key also copies keys.
        # Flow: get_public_key(ed25519, rsa) → keygen → keyscan → copy_to_user → get_public_key(ed25519)
        mock_ssh_for_git.run_command = AsyncMock(
            side_effect=[
                ("", "", 1),  # get_public_key: no ed25519
                ("", "", 1),  # get_public_key: no rsa
                ("", "", 0),  # ssh-keygen
                ("", "", 0),  # ssh-keyscan known_hosts
                ("", "", 0),  # _copy_key_to_user (mkdir+cp+chown)
                ("ssh-ed25519 NEWKEY autodev@keygen-srv", "", 0),  # get_public_key: ed25519
            ]
        )

        resp = await client.post(f"/api/workspace-servers/{server_id}/git-access/generate-key")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_key"] is True
        assert "NEWKEY" in data["public_key"]

    async def test_generate_not_found(self, client: AsyncClient, mock_ssh_for_git):
        resp = await client.post("/api/workspace-servers/999/git-access/generate-key")
        assert resp.status_code == 404