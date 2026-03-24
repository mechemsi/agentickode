# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for workspace readiness API endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.models.readiness import WorkspaceReadiness


@pytest.fixture
def mock_readiness_row():
    """Return a mock WorkspaceReadiness row."""
    row = MagicMock(spec=WorkspaceReadiness)
    row.id = 1
    row.project_id = "proj-1"
    row.workspace_server_id = 1
    row.validation_status = "passed"
    row.validated_at = datetime.now(UTC)
    row.expires_at = datetime.now(UTC) + timedelta(days=7)
    row.check_results = [
        {
            "name": "node_runtime",
            "status": "pass",
            "category": "runtime",
            "command": "node --version",
            "output": "v20",
            "duration_s": 0.1,
            "fix_suggestion": None,
        }
    ]
    row.validation_report = {
        "summary": "All 1 checks passed",
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "failures": [],
    }
    row.created_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    return row


class TestReadinessAPI:
    async def test_list_server_readiness(self, mock_readiness_row):
        with (
            patch("backend.api.servers.readiness.WorkspaceServerRepository") as mock_srv_repo_cls,
            patch("backend.api.servers.readiness.WorkspaceReadinessRepository") as mock_repo_cls,
        ):
            mock_srv_repo = mock_srv_repo_cls.return_value
            mock_srv_repo.get_by_id = AsyncMock(return_value=MagicMock(id=1))
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_for_server = AsyncMock(return_value=[mock_readiness_row])

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/workspace-servers/1/readiness")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["project_id"] == "proj-1"

    async def test_list_server_readiness_not_found(self):
        with patch("backend.api.servers.readiness.WorkspaceServerRepository") as mock_srv_repo_cls:
            mock_srv_repo = mock_srv_repo_cls.return_value
            mock_srv_repo.get_by_id = AsyncMock(return_value=None)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/workspace-servers/999/readiness")
            assert resp.status_code == 404

    async def test_get_readiness(self, mock_readiness_row):
        with patch("backend.api.servers.readiness.WorkspaceReadinessRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get = AsyncMock(return_value=mock_readiness_row)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/workspace-servers/1/projects/proj-1/readiness")
            assert resp.status_code == 200
            data = resp.json()
            assert data["validation_status"] == "passed"
            assert data["is_expired"] is False

    async def test_get_readiness_not_found(self):
        with patch("backend.api.servers.readiness.WorkspaceReadinessRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get = AsyncMock(return_value=None)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/workspace-servers/1/projects/proj-1/readiness")
            assert resp.status_code == 404

    async def test_trigger_validation(self, mock_readiness_row):
        with (
            patch("backend.api.servers.readiness.WorkspaceServerRepository") as mock_srv_repo_cls,
            patch("backend.api.servers.readiness.ProjectConfigRepository") as mock_proj_repo_cls,
            patch("backend.api.servers.readiness.WorkspaceReadinessRepository") as mock_repo_cls,
            patch("backend.api.servers.readiness.WorkspaceReadinessService") as mock_svc_cls,
            patch("backend.api.servers.readiness.SSHService"),
        ):
            mock_srv_repo = mock_srv_repo_cls.return_value
            server = MagicMock(id=1, workspace_root="/workspaces", worker_user="coder")
            mock_srv_repo.get_by_id = AsyncMock(return_value=server)

            mock_proj_repo = mock_proj_repo_cls.return_value
            project = MagicMock(workspace_path="myproj", workspace_config={})
            mock_proj_repo.get_by_id = AsyncMock(return_value=project)

            mock_svc = mock_svc_cls.return_value
            from backend.services.workspace.readiness_service import ValidationReport

            mock_svc.validate = AsyncMock(
                return_value=ValidationReport(passed=True, summary="All 1 checks passed", checks=[])
            )

            mock_repo = mock_repo_cls.return_value
            mock_repo.upsert = AsyncMock(return_value=mock_readiness_row)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/workspace-servers/1/projects/proj-1/validate")
            assert resp.status_code == 200
