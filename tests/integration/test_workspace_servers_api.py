# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for workspace servers API."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from backend.services.workspace.agent_discovery import AgentInfo
from backend.services.workspace.project_discovery import DiscoveredProject
from backend.services.workspace.ssh_service import SSHTestResult as SSHTestResultData


@pytest.fixture(autouse=True)
def mock_setup_service():
    """Prevent ServerSetupService from running background tasks during tests."""
    with patch("backend.api.servers.workspace_servers.ServerSetupService") as mock_cls:
        mock_cls.return_value.kick_off_setup = MagicMock()  # sync method
        mock_cls.return_value.retry_setup = AsyncMock()
        yield mock_cls


@pytest.fixture
def mock_ssh_service():
    """Mock SSH that succeeds for connection test."""
    with patch("backend.api.servers.workspace_servers.SSHService") as mock_cls:
        instance = AsyncMock()
        mock_cls.return_value = instance
        mock_cls.for_server = lambda server: instance
        instance.test_connection = AsyncMock(
            return_value=SSHTestResultData(success=True, latency_ms=5.0)
        )
        yield instance


@pytest.fixture
def mock_ssh_with_discovery():
    """Mock SSH + AgentDiscovery + ProjectDiscovery for scan endpoints."""
    with (
        patch("backend.api.servers.workspace_servers.SSHService") as mock_cls,
        patch("backend.api.servers.workspace_servers.AgentDiscoveryService") as mock_agent_cls,
        patch("backend.api.servers.workspace_servers.ProjectDiscoveryService") as mock_proj_cls,
    ):
        instance = AsyncMock()
        mock_cls.return_value = instance
        mock_cls.for_server = lambda server: instance
        instance.test_connection = AsyncMock(
            return_value=SSHTestResultData(success=True, latency_ms=5.0)
        )

        # Empty discovery by default
        mock_agent_cls.return_value.discover_all = AsyncMock(return_value=[])
        mock_proj_cls.return_value.scan_workspace = AsyncMock(return_value=[])

        yield {
            "ssh": instance,
            "agent_cls": mock_agent_cls,
            "proj_cls": mock_proj_cls,
        }


def _sample_agents_and_projects():
    """Return sample agents and projects for discovery mocking."""
    agents = [
        AgentInfo(
            agent_name="aider",
            agent_type="cli_binary",
            path="/usr/bin/aider",
            version="0.40.0",
            available=True,
            metadata={"lang": "python"},
        ),
        AgentInfo(
            agent_name="openhands",
            agent_type="api_service",
            available=True,
        ),
    ]
    projects = [
        DiscoveredProject(
            path="/workspaces/my-app",
            remote_url="https://gitea.local/org/my-app.git",
            owner="org",
            name="my-app",
            git_provider="gitea",
        ),
        DiscoveredProject(
            path="/workspaces/api-svc",
            remote_url="git@github.com:org/api-svc.git",
            owner="org",
            name="api-svc",
            git_provider="github",
        ),
    ]
    return agents, projects


class TestCreateWorkspaceServer:
    async def test_create_success(self, client: AsyncClient):
        resp = await client.post(
            "/api/workspace-servers",
            json={
                "name": "coding-01",
                "hostname": "10.10.50.25",
                "port": 22,
                "username": "root",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "coding-01"
        assert data["hostname"] == "10.10.50.25"
        assert data["status"] == "setting_up"
        assert data["workspace_root"] == "/workspaces"

    async def test_create_with_defaults(self, client: AsyncClient):
        """Create with minimal fields, verify defaults are applied."""
        resp = await client.post(
            "/api/workspace-servers",
            json={"name": "min-srv", "hostname": "10.0.0.1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["port"] == 22
        assert data["username"] == "root"
        assert data["workspace_root"] == "/workspaces"
        assert data["ssh_key_path"] is None
        assert data["status"] == "setting_up"
        assert data["worker_user"] == "coder"

    async def test_create_has_no_agents_initially(self, client: AsyncClient):
        """Newly created server should have no agents (setup runs in background)."""
        resp = await client.post(
            "/api/workspace-servers",
            json={"name": "new-srv", "hostname": "10.0.0.1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_count"] == 0
        assert data["project_count"] == 0
        assert data["agents"] == []

    async def test_create_kicks_off_setup(self, client: AsyncClient, mock_setup_service):
        """Create should trigger background setup."""
        resp = await client.post(
            "/api/workspace-servers",
            json={"name": "setup-srv", "hostname": "10.0.0.1"},
        )
        assert resp.status_code == 201
        mock_setup_service.return_value.kick_off_setup.assert_called_once()


class TestListWorkspaceServers:
    async def test_empty_list(self, client: AsyncClient):
        resp = await client.get("/api/workspace-servers")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, client: AsyncClient):
        await client.post(
            "/api/workspace-servers",
            json={"name": "srv-1", "hostname": "10.0.0.1"},
        )
        resp = await client.get("/api/workspace-servers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "srv-1"
        assert "agent_count" in data[0]
        assert "project_count" in data[0]


class TestGetWorkspaceServer:
    async def test_not_found(self, client: AsyncClient):
        resp = await client.get("/api/workspace-servers/999")
        assert resp.status_code == 404

    async def test_get_detail(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "detail-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.get(f"/api/workspace-servers/{server_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "detail-srv"
        assert "agents" in data

    async def test_get_detail_with_agents(self, client: AsyncClient, mock_ssh_with_discovery):
        """GET detail returns agents list after scan discovers them."""
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "agents-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]

        # Scan to discover agents and projects
        agents, projects = _sample_agents_and_projects()
        mock_ssh_with_discovery["agent_cls"].return_value.discover_all = AsyncMock(
            return_value=agents
        )
        mock_ssh_with_discovery["proj_cls"].return_value.scan_workspace = AsyncMock(
            return_value=projects
        )

        scan_resp = await client.post(f"/api/workspace-servers/{server_id}/scan")
        assert scan_resp.status_code == 200

        # Now get detail
        resp = await client.get(f"/api/workspace-servers/{server_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_count"] == 2
        assert data["project_count"] == 2
        assert len(data["agents"]) == 2
        # Verify agent fields
        aider_agent = next(a for a in data["agents"] if a["agent_name"] == "aider")
        assert aider_agent["agent_type"] == "cli_binary"
        assert aider_agent["path"] == "/usr/bin/aider"
        assert aider_agent["version"] == "0.40.0"
        assert aider_agent["available"] is True
        assert "discovered_at" in aider_agent


class TestUpdateWorkspaceServer:
    async def test_update(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "upd-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.put(
            f"/api/workspace-servers/{server_id}",
            json={"name": "renamed-srv"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed-srv"

    async def test_update_not_found(self, client: AsyncClient):
        resp = await client.put("/api/workspace-servers/999", json={"name": "nope"})
        assert resp.status_code == 404

    async def test_update_multiple_fields(self, client: AsyncClient):
        """Update several fields at once."""
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "multi-upd", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.put(
            f"/api/workspace-servers/{server_id}",
            json={
                "name": "updated-name",
                "hostname": "10.0.0.2",
                "port": 2222,
                "username": "deploy",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "updated-name"
        assert data["hostname"] == "10.0.0.2"
        assert data["port"] == 2222
        assert data["username"] == "deploy"

    async def test_update_partial_preserves_other_fields(self, client: AsyncClient):
        """A partial update should not reset other fields."""
        create_resp = await client.post(
            "/api/workspace-servers",
            json={
                "name": "partial-upd",
                "hostname": "10.0.0.5",
                "port": 2222,
                "username": "admin",
            },
        )
        server_id = create_resp.json()["id"]
        resp = await client.put(
            f"/api/workspace-servers/{server_id}",
            json={"name": "new-name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new-name"
        assert data["hostname"] == "10.0.0.5"
        assert data["port"] == 2222
        assert data["username"] == "admin"


class TestDeleteWorkspaceServer:
    async def test_delete(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "del-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/workspace-servers/{server_id}")
        assert resp.status_code == 204

        # Verify gone
        resp = await client.get(f"/api/workspace-servers/{server_id}")
        assert resp.status_code == 404

    async def test_delete_not_found(self, client: AsyncClient):
        resp = await client.delete("/api/workspace-servers/999")
        assert resp.status_code == 404

    async def test_delete_nullifies_project_fk(self, client: AsyncClient, mock_ssh_with_discovery):
        """Deleting a workspace server should nullify workspace_server_id on linked projects."""
        # Create server
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "fk-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]

        # Scan to discover projects
        agents, projects = _sample_agents_and_projects()
        mock_ssh_with_discovery["agent_cls"].return_value.discover_all = AsyncMock(
            return_value=agents
        )
        mock_ssh_with_discovery["proj_cls"].return_value.scan_workspace = AsyncMock(
            return_value=projects
        )
        scan_resp = await client.post(f"/api/workspace-servers/{server_id}/scan")
        assert scan_resp.status_code == 200
        assert scan_resp.json()["projects_imported"] == 2

        # Verify projects are linked
        proj_resp = await client.get("/api/projects")
        assert proj_resp.status_code == 200
        projects_data = proj_resp.json()
        linked = [p for p in projects_data if p.get("workspace_server_id") == server_id]
        assert len(linked) == 2

        # Delete server
        resp = await client.delete(f"/api/workspace-servers/{server_id}")
        assert resp.status_code == 204

        # Verify projects still exist but FK is nullified
        proj_resp = await client.get("/api/projects")
        assert proj_resp.status_code == 200
        projects_data = proj_resp.json()
        assert len(projects_data) == 2
        for p in projects_data:
            assert p.get("workspace_server_id") is None


class TestSSHTest:
    async def test_test_endpoint(self, client: AsyncClient, mock_ssh_service):
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "test-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]

        resp = await client.post(f"/api/workspace-servers/{server_id}/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    async def test_test_endpoint_ssh_failure(self, client: AsyncClient):
        """Test endpoint when SSH fails."""
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "test-fail-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]

        # Make SSH fail for the test call
        with patch("backend.api.servers.workspace_servers.SSHService") as mock_cls:
            fail_instance = AsyncMock()
            mock_cls.for_server = lambda server: fail_instance
            fail_instance.test_connection = AsyncMock(
                return_value=SSHTestResultData(
                    success=False, latency_ms=100.0, error="Connection timed out"
                )
            )

            resp = await client.post(f"/api/workspace-servers/{server_id}/test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False
            assert data["error"] == "Connection timed out"
            assert data["latency_ms"] == 100.0

        # Verify server status was updated to error
        detail = await client.get(f"/api/workspace-servers/{server_id}")
        assert detail.json()["status"] == "error"
        assert detail.json()["error_message"] == "Connection timed out"

    async def test_test_endpoint_not_found(self, client: AsyncClient):
        resp = await client.post("/api/workspace-servers/999/test")
        assert resp.status_code == 404

    async def test_test_success_updates_status(self, client: AsyncClient):
        """SSH test success should update server status to online."""
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "recover-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]
        assert create_resp.json()["status"] == "setting_up"

        # SSH test succeeds
        with patch("backend.api.servers.workspace_servers.SSHService") as mock_cls:
            ok_instance = AsyncMock()
            mock_cls.for_server = lambda server: ok_instance
            ok_instance.test_connection = AsyncMock(
                return_value=SSHTestResultData(success=True, latency_ms=2.0)
            )
            resp = await client.post(f"/api/workspace-servers/{server_id}/test")
            assert resp.status_code == 200
            assert resp.json()["success"] is True

        # Verify server status updated to online
        detail = await client.get(f"/api/workspace-servers/{server_id}")
        assert detail.json()["status"] == "online"
        assert detail.json()["last_seen_at"] is not None
        assert detail.json()["error_message"] is None


class TestScan:
    async def test_scan_endpoint(self, client: AsyncClient, mock_ssh_with_discovery):
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "scan-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]

        resp = await client.post(f"/api/workspace-servers/{server_id}/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents_found" in data
        assert "projects_found" in data
        assert "projects_imported" in data

    async def test_scan_not_found(self, client: AsyncClient):
        resp = await client.post("/api/workspace-servers/999/scan")
        assert resp.status_code == 404

    async def test_scan_discovers_agents_and_projects(self, client: AsyncClient):
        """Scan with agents and projects discovered."""
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "scan-full", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]

        # Set up mocks for scan that discover agents and projects
        agents = [
            AgentInfo(
                agent_name="claude",
                agent_type="cli_binary",
                path="/usr/bin/claude",
                version="1.0.0",
                available=True,
            ),
        ]
        projects = [
            DiscoveredProject(
                path="/workspaces/new-proj",
                remote_url="https://gitea.local/team/new-proj.git",
                owner="team",
                name="new-proj",
                git_provider="gitea",
            ),
        ]
        with (
            patch("backend.api.servers.workspace_servers.SSHService") as mock_cls,
            patch("backend.api.servers.workspace_servers.AgentDiscoveryService") as mock_agent_cls,
            patch("backend.api.servers.workspace_servers.ProjectDiscoveryService") as mock_proj_cls,
        ):
            scan_ssh = AsyncMock()
            mock_cls.for_server = lambda server: scan_ssh
            scan_ssh.test_connection = AsyncMock(
                return_value=SSHTestResultData(success=True, latency_ms=5.0)
            )
            mock_agent_cls.return_value.discover_all = AsyncMock(return_value=agents)
            mock_proj_cls.return_value.scan_workspace = AsyncMock(return_value=projects)

            resp = await client.post(f"/api/workspace-servers/{server_id}/scan")
            assert resp.status_code == 200
            data = resp.json()
            assert data["agents_found"] == 1
            assert data["projects_found"] == 1
            assert data["projects_imported"] == 1

        # Verify agents are visible on the server detail
        detail = await client.get(f"/api/workspace-servers/{server_id}")
        assert detail.status_code == 200
        assert len(detail.json()["agents"]) == 1
        assert detail.json()["agents"][0]["agent_name"] == "claude"

    async def test_scan_skips_existing_projects(self, client: AsyncClient):
        """When a project already exists in DB, scan should not re-import it."""
        # Create server
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "scan-dup", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]

        agents, projects = _sample_agents_and_projects()

        # First scan: imports projects
        with (
            patch("backend.api.servers.workspace_servers.SSHService") as mock_cls,
            patch("backend.api.servers.workspace_servers.AgentDiscoveryService") as mock_agent_cls,
            patch("backend.api.servers.workspace_servers.ProjectDiscoveryService") as mock_proj_cls,
        ):
            scan_ssh = AsyncMock()
            mock_cls.for_server = lambda server: scan_ssh
            scan_ssh.test_connection = AsyncMock(
                return_value=SSHTestResultData(success=True, latency_ms=5.0)
            )
            mock_agent_cls.return_value.discover_all = AsyncMock(return_value=agents)
            mock_proj_cls.return_value.scan_workspace = AsyncMock(return_value=projects)

            resp = await client.post(f"/api/workspace-servers/{server_id}/scan")
            assert resp.status_code == 200
            assert resp.json()["projects_imported"] == 2

        # Second scan with same projects but fresh agent objects
        same_projects = [
            DiscoveredProject(
                path="/workspaces/my-app",
                remote_url="https://gitea.local/org/my-app.git",
                owner="org",
                name="my-app",
                git_provider="gitea",
            ),
            DiscoveredProject(
                path="/workspaces/api-svc",
                remote_url="git@github.com:org/api-svc.git",
                owner="org",
                name="api-svc",
                git_provider="github",
            ),
        ]
        fresh_agents = [
            AgentInfo(
                agent_name="claude",
                agent_type="cli_binary",
                path="/usr/bin/claude",
                version="2.0.0",
                available=True,
            ),
        ]
        with (
            patch("backend.api.servers.workspace_servers.SSHService") as mock_cls,
            patch("backend.api.servers.workspace_servers.AgentDiscoveryService") as mock_agent_cls,
            patch("backend.api.servers.workspace_servers.ProjectDiscoveryService") as mock_proj_cls,
        ):
            scan_ssh = AsyncMock()
            mock_cls.for_server = lambda server: scan_ssh
            scan_ssh.test_connection = AsyncMock(
                return_value=SSHTestResultData(success=True, latency_ms=5.0)
            )
            mock_agent_cls.return_value.discover_all = AsyncMock(return_value=fresh_agents)
            mock_proj_cls.return_value.scan_workspace = AsyncMock(return_value=same_projects)

            resp = await client.post(f"/api/workspace-servers/{server_id}/scan")
            assert resp.status_code == 200
            data = resp.json()
            assert data["projects_found"] == 2
            assert data["projects_imported"] == 0


class TestSetupLog:
    async def test_get_setup_log(self, client: AsyncClient):
        """GET setup-log returns the setup log for a server."""
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "log-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.get(f"/api/workspace-servers/{server_id}/setup-log")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    async def test_get_setup_log_not_found(self, client: AsyncClient):
        resp = await client.get("/api/workspace-servers/999/setup-log")
        assert resp.status_code == 404


class TestRetrySetup:
    async def test_retry_setup(self, client: AsyncClient, mock_setup_service):
        """POST retry-setup should trigger setup again."""
        create_resp = await client.post(
            "/api/workspace-servers",
            json={"name": "retry-srv", "hostname": "10.0.0.1"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.post(f"/api/workspace-servers/{server_id}/retry-setup")
        assert resp.status_code == 200
        assert resp.json()["status"] == "setup_retrying"
        # kick_off_setup called twice: once during create, once during retry
        assert mock_setup_service.return_value.kick_off_setup.call_count == 2

    async def test_retry_setup_not_found(self, client: AsyncClient):
        resp = await client.post("/api/workspace-servers/999/retry-setup")
        assert resp.status_code == 404
