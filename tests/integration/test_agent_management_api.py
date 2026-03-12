# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for agent management API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.services.workspace.ssh_service import SSHTestResult as SSHTestResultData
from backend.services.workspace.worker_user_service import WorkerUserInfo


@pytest.fixture(autouse=True)
async def _seed_agent_settings(db_engine):
    """Seed agent settings so the management API can find them."""
    from backend.seed import _seed_agent_settings

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await _seed_agent_settings(session)


@pytest.fixture
def mock_ssh_for_agents():
    """Mock SSH for agent management tests."""
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
            patch("backend.api.servers.agent_management.SSHService") as am_mock_cls,
            patch("backend.api.servers.agent_management.WorkerUserService") as am_user_mock_cls,
        ):
            mock_agent_cls.return_value.discover_all = AsyncMock(return_value=[])
            mock_proj_cls.return_value.scan_workspace = AsyncMock(return_value=[])

            am_instance = AsyncMock()
            am_mock_cls.for_server = lambda server: am_instance
            am_instance.run_command = AsyncMock(return_value=("", "", 1))

            # Mock WorkerUserService.setup() to return a ready user
            am_user_mock = AsyncMock()
            am_user_mock.setup.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=[]
            )
            am_user_mock_cls.return_value = am_user_mock

            yield am_instance


class TestGetAgentStatus:
    async def test_status_returns_all_agents(self, client: AsyncClient, mock_ssh_for_agents):
        # Create a server first
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "agent-test-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]

        # All agents not installed (default mock returns exit code 1)
        resp = await client.post(f"/api/workspace-servers/{server_id}/agents/status")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 8
        names = {a["agent_name"] for a in data["agents"]}
        assert names == {
            "claude",
            "codex",
            "opencode",
            "aider",
            "gemini",
            "kimi",
            "copilot",
            "openhands",
        }

    async def test_status_404_for_missing_server(self, client: AsyncClient, mock_ssh_for_agents):
        resp = await client.post("/api/workspace-servers/999/agents/status")
        assert resp.status_code == 404


class TestInstallAgent:
    async def test_install_triggers_command(self, client: AsyncClient, mock_ssh_for_agents):
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "install-test-srv", "hostname": "10.0.0.2"},
        )
        server_id = create_resp.json()["id"]

        call_count = 0

        async def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("", "", 0)  # prereq OK
            if call_count == 2:
                return ("", "", 0)  # install OK
            return ("/usr/bin/claude", "", 0)  # verify OK

        mock_ssh_for_agents.run_command = AsyncMock(side_effect=side_effect)

        resp = await client.post(
            f"/api/workspace-servers/{server_id}/agents/install",
            json={"agent_name": "claude"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["agent_name"] == "claude"

    async def test_install_404_for_missing_server(self, client: AsyncClient, mock_ssh_for_agents):
        resp = await client.post(
            "/api/workspace-servers/999/agents/install",
            json={"agent_name": "claude"},
        )
        assert resp.status_code == 404

    async def test_install_unknown_agent(self, client: AsyncClient, mock_ssh_for_agents):
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "unknown-agent-srv", "hostname": "10.0.0.3"},
        )
        server_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/workspace-servers/{server_id}/agents/install",
            json={"agent_name": "nonexistent"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Unknown agent" in data["error"]