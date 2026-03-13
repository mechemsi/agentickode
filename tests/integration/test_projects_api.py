# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for the Projects API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest


class TestProjectsCRUD:
    @pytest.fixture()
    def sample_project(self):
        return {
            "project_id": "proj-test-1",
            "project_slug": "test-project",
            "repo_owner": "test-org",
            "repo_name": "test-repo",
            "default_branch": "main",
            "task_source": "plane",
            "git_provider": "gitea",
        }

    async def test_list_empty(self, client):
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_project(self, client, sample_project):
        resp = await client.post("/api/projects", json=sample_project)
        assert resp.status_code == 201
        data = resp.json()
        assert data["project_id"] == "proj-test-1"
        assert data["project_slug"] == "test-project"
        assert data["repo_owner"] == "test-org"
        assert "created_at" in data

    async def test_create_project_uses_detected_branch(
        self, client, sample_project, mock_get_default_branch
    ):
        """Detected branch from provider API overrides user-supplied value."""
        mock_get_default_branch.return_value = "develop"
        sample_project["default_branch"] = "main"
        resp = await client.post("/api/projects", json=sample_project)
        assert resp.status_code == 201
        assert resp.json()["default_branch"] == "develop"

    async def test_create_duplicate_returns_409(self, client, sample_project):
        await client.post("/api/projects", json=sample_project)
        resp = await client.post("/api/projects", json=sample_project)
        assert resp.status_code == 409

    async def test_create_repo_not_found_returns_422(self, client, sample_project):
        import httpx

        mock_response = AsyncMock()
        mock_response.status_code = 404

        with patch(
            "backend.api.projects.get_default_branch",
            side_effect=httpx.HTTPStatusError(
                "not found", request=AsyncMock(), response=mock_response
            ),
        ):
            resp = await client.post("/api/projects", json=sample_project)
        assert resp.status_code == 422
        assert "not found" in resp.json()["detail"].lower()

    async def test_create_auth_failure_returns_422(self, client, sample_project):
        import httpx

        mock_response = AsyncMock()
        mock_response.status_code = 401

        with patch(
            "backend.api.projects.get_default_branch",
            side_effect=httpx.HTTPStatusError(
                "unauthorized", request=AsyncMock(), response=mock_response
            ),
        ):
            resp = await client.post("/api/projects", json=sample_project)
        assert resp.status_code == 422
        assert "Authentication failed" in resp.json()["detail"]

    async def test_create_provider_unreachable_returns_422(self, client, sample_project):
        import httpx

        with patch(
            "backend.api.projects.get_default_branch",
            side_effect=httpx.RequestError("connection refused"),
        ):
            resp = await client.post("/api/projects", json=sample_project)
        assert resp.status_code == 422
        assert "Cannot reach" in resp.json()["detail"]

    async def test_get_project(self, client, sample_project):
        await client.post("/api/projects", json=sample_project)
        resp = await client.get("/api/projects/proj-test-1")
        assert resp.status_code == 200
        assert resp.json()["project_slug"] == "test-project"

    async def test_get_nonexistent_returns_404(self, client):
        resp = await client.get("/api/projects/nonexistent")
        assert resp.status_code == 404

    async def test_update_project(self, client, sample_project):
        await client.post("/api/projects", json=sample_project)
        resp = await client.put(
            "/api/projects/proj-test-1",
            json={"repo_owner": "new-org"},
        )
        assert resp.status_code == 200
        assert resp.json()["repo_owner"] == "new-org"

    async def test_update_nonexistent_returns_404(self, client):
        resp = await client.put("/api/projects/nope", json={"repo_owner": "x"})
        assert resp.status_code == 404

    async def test_delete_project(self, client, sample_project):
        await client.post("/api/projects", json=sample_project)
        resp = await client.delete("/api/projects/proj-test-1")
        assert resp.status_code == 204
        resp = await client.get("/api/projects/proj-test-1")
        assert resp.status_code == 404

    async def test_delete_nonexistent_returns_404(self, client):
        resp = await client.delete("/api/projects/nope")
        assert resp.status_code == 404

    async def test_list_returns_created_projects(self, client, sample_project):
        await client.post("/api/projects", json=sample_project)
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
