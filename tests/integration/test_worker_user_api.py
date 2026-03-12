# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for worker user API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from backend.models import WorkspaceServer


@pytest.fixture()
async def workspace_server(db_session):
    """Create a workspace server in the test DB."""
    server = WorkspaceServer(
        name="test-ws",
        hostname="10.0.0.1",
        port=22,
        username="root",
        workspace_root="/workspaces",
        status="online",
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    return server


class TestSetupWorkerUser:
    async def test_setup_success(self, client: AsyncClient, workspace_server):
        mock_info = AsyncMock()
        mock_info.return_value = AsyncMock(
            exists=True,
            username="coder",
            agents=["claude"],
            error=None,
        )
        with patch("backend.api.servers.worker_user.SSHService") as mock_ssh_cls:
            mock_ssh_cls.for_server.return_value = AsyncMock()
            with patch("backend.api.servers.worker_user.WorkerUserService") as mock_svc_cls:
                mock_svc_cls.return_value.setup = mock_info
                resp = await client.post(
                    f"/api/workspace-servers/{workspace_server.id}/worker-user/setup",
                    json={"username": "coder"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["username"] == "coder"
        assert data["status"] == "ready"
        assert "claude" in data["agents"]

    async def test_setup_default_username(self, client: AsyncClient, workspace_server):
        mock_info = AsyncMock()
        mock_info.return_value = AsyncMock(
            exists=True,
            username="coder",
            agents=[],
            error=None,
        )
        with patch("backend.api.servers.worker_user.SSHService") as mock_ssh_cls:
            mock_ssh_cls.for_server.return_value = AsyncMock()
            with patch("backend.api.servers.worker_user.WorkerUserService") as mock_svc_cls:
                mock_svc_cls.return_value.setup = mock_info
                resp = await client.post(
                    f"/api/workspace-servers/{workspace_server.id}/worker-user/setup",
                )

        assert resp.status_code == 200
        assert resp.json()["username"] == "coder"

    async def test_setup_error(self, client: AsyncClient, workspace_server):
        mock_info = AsyncMock()
        mock_info.return_value = AsyncMock(
            exists=False,
            username="coder",
            agents=[],
            error="useradd failed",
        )
        with patch("backend.api.servers.worker_user.SSHService") as mock_ssh_cls:
            mock_ssh_cls.for_server.return_value = AsyncMock()
            with patch("backend.api.servers.worker_user.WorkerUserService") as mock_svc_cls:
                mock_svc_cls.return_value.setup = mock_info
                resp = await client.post(
                    f"/api/workspace-servers/{workspace_server.id}/worker-user/setup",
                    json={"username": "coder"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["status"] == "error"

    async def test_setup_server_not_found(self, client: AsyncClient):
        resp = await client.post("/api/workspace-servers/999/worker-user/setup")
        assert resp.status_code == 404


class TestCheckWorkerUser:
    async def test_check_no_worker_user(self, client: AsyncClient, workspace_server):
        resp = await client.post(
            f"/api/workspace-servers/{workspace_server.id}/worker-user/status",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] is None
        assert data["status"] is None

    async def test_check_server_not_found(self, client: AsyncClient):
        resp = await client.post("/api/workspace-servers/999/worker-user/status")
        assert resp.status_code == 404


class TestSyncWorkerUser:
    async def test_sync_no_worker_user(self, client: AsyncClient, workspace_server):
        resp = await client.post(
            f"/api/workspace-servers/{workspace_server.id}/worker-user/sync",
        )
        assert resp.status_code == 400

    async def test_sync_server_not_found(self, client: AsyncClient):
        resp = await client.post("/api/workspace-servers/999/worker-user/sync")
        assert resp.status_code == 404


class TestSetWorkerUserPassword:
    async def test_set_password_success(self, client: AsyncClient, workspace_server, db_session):
        workspace_server.worker_user = "coder"
        workspace_server.worker_user_status = "ready"
        db_session.add(workspace_server)
        await db_session.commit()

        mock_info = AsyncMock()
        mock_info.return_value = AsyncMock(
            exists=True,
            username="coder",
            agents=[],
            error=None,
        )
        with patch("backend.api.servers.worker_user.SSHService") as mock_ssh_cls:
            mock_ssh_cls.for_server.return_value = AsyncMock()
            with patch("backend.api.servers.worker_user.WorkerUserService") as mock_svc_cls:
                mock_svc_cls.return_value.set_password = mock_info
                resp = await client.post(
                    f"/api/workspace-servers/{workspace_server.id}/worker-user/set-password",
                    json={"password": "s3cret"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["error"] is None

    async def test_set_password_no_worker_user(self, client: AsyncClient, workspace_server):
        resp = await client.post(
            f"/api/workspace-servers/{workspace_server.id}/worker-user/set-password",
            json={"password": "s3cret"},
        )
        assert resp.status_code == 400

    async def test_set_password_server_not_found(self, client: AsyncClient):
        resp = await client.post(
            "/api/workspace-servers/999/worker-user/set-password",
            json={"password": "s3cret"},
        )
        assert resp.status_code == 404


class TestDeleteWorkerUser:
    async def test_delete_clears_config(self, client: AsyncClient, workspace_server, db_session):
        # Set worker_user first
        workspace_server.worker_user = "coder"
        workspace_server.worker_user_status = "ready"
        db_session.add(workspace_server)
        await db_session.commit()

        resp = await client.delete(
            f"/api/workspace-servers/{workspace_server.id}/worker-user",
        )
        assert resp.status_code == 204

    async def test_delete_server_not_found(self, client: AsyncClient):
        resp = await client.delete("/api/workspace-servers/999/worker-user")
        assert resp.status_code == 404