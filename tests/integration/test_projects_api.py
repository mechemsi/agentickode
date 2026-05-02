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


class TestProjectsIntegrationConfig:
    @pytest.fixture()
    def notion_project(self):
        return {
            "project_id": "notion-proj",
            "project_slug": "notion-proj",
            "repo_owner": "owner",
            "repo_name": "repo",
            "default_branch": "main",
            "task_source": "notion",
            "git_provider": "github",
            "integration_config": {
                "notion_api_key": "secret_plaintext",
                "notion_database_id": "db-123",
                "notion_status_property": "Status",
            },
        }

    async def test_create_encrypts_and_redacts_notion_api_key(
        self, client, db_session, notion_project
    ):
        from sqlalchemy import select

        from backend.models import ProjectConfig
        from backend.services.encryption import decrypt_value

        resp = await client.post("/api/projects", json=notion_project)
        assert resp.status_code == 201
        cfg = resp.json()["integration_config"]
        # Plaintext key must not be echoed back
        assert "notion_api_key" not in cfg
        assert "notion_api_key_enc" not in cfg
        # Boolean flag indicates a secret is stored
        assert cfg.get("has_notion_api_key") is True
        # Non-secret fields pass through unchanged
        assert cfg["notion_database_id"] == "db-123"
        assert cfg["notion_status_property"] == "Status"

        # Verify the persisted value is actually encrypted
        row = (
            await db_session.execute(
                select(ProjectConfig).where(ProjectConfig.project_id == "notion-proj")
            )
        ).scalar_one()
        stored = row.integration_config or {}
        assert "notion_api_key" not in stored
        assert stored.get("notion_api_key_enc")
        assert decrypt_value(stored["notion_api_key_enc"]) == "secret_plaintext"

    async def test_update_merges_integration_config_preserving_secret(self, client, notion_project):
        # First, create with the API key
        resp = await client.post("/api/projects", json=notion_project)
        assert resp.status_code == 201

        # Update with only a non-secret field; secret must survive the merge
        resp = await client.put(
            "/api/projects/notion-proj",
            json={"integration_config": {"notion_database_id": "db-456"}},
        )
        assert resp.status_code == 200
        cfg = resp.json()["integration_config"]
        assert cfg["notion_database_id"] == "db-456"
        assert cfg.get("has_notion_api_key") is True

    async def test_polling_fields_round_trip(self, client, notion_project):
        notion_project["poll_enabled"] = True
        notion_project["poll_interval_minutes"] = 15
        resp = await client.post("/api/projects", json=notion_project)
        assert resp.status_code == 201
        body = resp.json()
        assert body["poll_enabled"] is True
        assert body["poll_interval_minutes"] == 15
