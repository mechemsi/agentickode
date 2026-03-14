# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for server-scoped project listing endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from backend.services.workspace.ssh_service import SSHTestResult as SSHTestResultData


@pytest.fixture
def mock_ssh_for_projects():
    """Mock SSH so workspace server creation and project validation succeed."""
    with patch("backend.api.servers.workspace_servers_discovery.SSHService") as ws_mock_cls:
        ws_instance = AsyncMock()
        ws_mock_cls.return_value = ws_instance
        ws_mock_cls.for_server = lambda server: ws_instance
        ws_instance.test_connection = AsyncMock(
            return_value=SSHTestResultData(success=True, latency_ms=5.0)
        )

        # Also mock SSHService in projects API (for create_project SSH validation)
        proj_ssh_instance = AsyncMock()
        proj_ssh_instance.run_command = AsyncMock(return_value=("ref HEAD", "", 0))
        with (
            patch(
                "backend.api.projects.SSHService",
                **{"for_server.return_value": proj_ssh_instance},
            ),
            patch(
                "backend.api.servers.workspace_servers_discovery.AgentDiscoveryService"
            ) as mock_agent_cls,
            patch(
                "backend.api.servers.workspace_servers_discovery.ProjectDiscoveryService"
            ) as mock_proj_cls,
        ):
            mock_agent_cls.return_value.discover_all = AsyncMock(return_value=[])
            mock_proj_cls.return_value.scan_workspace = AsyncMock(return_value=[])
            yield


class TestListServerProjects:
    async def test_returns_empty_for_server_with_no_projects(
        self, client: AsyncClient, mock_ssh_for_projects
    ):
        resp = await client.post(
            "/api/workspace-servers",
            json={"name": "proj-test-srv", "hostname": "10.0.0.1"},
        )
        server_id = resp.json()["id"]

        resp = await client.get(f"/api/workspace-servers/{server_id}/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_projects_linked_to_server(
        self, client: AsyncClient, mock_ssh_for_projects
    ):
        resp = await client.post(
            "/api/workspace-servers",
            json={"name": "proj-srv-2", "hostname": "10.0.0.2"},
        )
        server_id = resp.json()["id"]

        # Create a project linked to this server
        await client.post(
            "/api/projects",
            json={
                "project_id": "proj-a",
                "project_slug": "proj-a",
                "repo_owner": "org",
                "repo_name": "repo-a",
                "workspace_server_id": server_id,
            },
        )
        # Create an unlinked project
        await client.post(
            "/api/projects",
            json={
                "project_id": "proj-b",
                "project_slug": "proj-b",
                "repo_owner": "org",
                "repo_name": "repo-b",
            },
        )

        resp = await client.get(f"/api/workspace-servers/{server_id}/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "proj-a"
        assert data[0]["workspace_server_id"] == server_id

    async def test_404_for_missing_server(self, client: AsyncClient, mock_ssh_for_projects):
        resp = await client.get("/api/workspace-servers/999/projects")
        assert resp.status_code == 404
