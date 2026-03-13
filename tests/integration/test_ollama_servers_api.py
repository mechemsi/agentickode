# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for Ollama servers API."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def mock_fetch_models():
    """Mock the Ollama API call so tests don't need a real server."""
    with patch("backend.api.ollama_servers._fetch_models") as mock:
        mock.return_value = (
            "online",
            [{"name": "qwen2.5-coder:32b", "size": 1000}],
            None,
        )
        yield mock


class TestCreateOllamaServer:
    async def test_create_success(self, client: AsyncClient):
        resp = await client.post(
            "/api/ollama-servers",
            json={"name": "gpu-01", "url": "http://10.10.50.20:11434"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "gpu-01"
        assert data["status"] == "online"
        assert len(data["cached_models"]) == 1

    async def test_create_sets_last_seen_at_when_online(self, client: AsyncClient):
        """When health check succeeds, last_seen_at should be set."""
        resp = await client.post(
            "/api/ollama-servers",
            json={"name": "seen-srv", "url": "http://10.0.0.1:11434"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "online"
        assert data["last_seen_at"] is not None
        assert data["error_message"] is None

    async def test_create_with_failed_health(self, client: AsyncClient, mock_fetch_models):
        mock_fetch_models.return_value = ("error", None, "Connection refused")
        resp = await client.post(
            "/api/ollama-servers",
            json={"name": "bad-gpu", "url": "http://10.10.50.99:11434"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "error"

    async def test_create_with_failed_health_full_check(
        self, client: AsyncClient, mock_fetch_models
    ):
        """When health check fails, server is still created but with error status."""
        mock_fetch_models.return_value = ("error", None, "Connection refused")
        resp = await client.post(
            "/api/ollama-servers",
            json={"name": "err-gpu", "url": "http://10.0.0.99:11434"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "error"
        assert data["error_message"] == "Connection refused"
        assert data["cached_models"] is None
        assert data["last_seen_at"] is None

    async def test_create_caches_model_details(self, client: AsyncClient, mock_fetch_models):
        """Verify that the model list from Ollama is cached."""
        mock_fetch_models.return_value = (
            "online",
            [
                {"name": "qwen2.5-coder:32b", "size": 19000000000},
                {"name": "devstral:24b", "size": 14000000000},
            ],
            None,
        )
        resp = await client.post(
            "/api/ollama-servers",
            json={"name": "models-srv", "url": "http://10.0.0.1:11434"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["cached_models"]) == 2
        model_names = [m["name"] for m in data["cached_models"]]
        assert "qwen2.5-coder:32b" in model_names
        assert "devstral:24b" in model_names


class TestListOllamaServers:
    async def test_empty(self, client: AsyncClient):
        resp = await client.get("/api/ollama-servers")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, client: AsyncClient):
        await client.post(
            "/api/ollama-servers",
            json={"name": "srv-1", "url": "http://10.0.0.1:11434"},
        )
        resp = await client.get("/api/ollama-servers")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestGetOllamaServer:
    async def test_not_found(self, client: AsyncClient):
        resp = await client.get("/api/ollama-servers/999")
        assert resp.status_code == 404

    async def test_get_detail(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "detail-srv", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.get(f"/api/ollama-servers/{server_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "detail-srv"


class TestUpdateOllamaServer:
    async def test_update(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "upd-srv", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.put(
            f"/api/ollama-servers/{server_id}",
            json={"name": "renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed"

    async def test_update_not_found(self, client: AsyncClient):
        resp = await client.put("/api/ollama-servers/999", json={"name": "nope"})
        assert resp.status_code == 404

    async def test_update_url(self, client: AsyncClient):
        """Update just the URL, name should be preserved."""
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "url-upd", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.put(
            f"/api/ollama-servers/{server_id}",
            json={"url": "http://10.0.0.2:11434"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "http://10.0.0.2:11434"
        assert data["name"] == "url-upd"

    async def test_update_preserves_cached_models(self, client: AsyncClient):
        """Updating name should not clear cached models."""
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "cache-upd", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]
        assert len(create_resp.json()["cached_models"]) == 1

        resp = await client.put(
            f"/api/ollama-servers/{server_id}",
            json={"name": "cache-upd-renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "cache-upd-renamed"
        # Models should still be there
        assert len(resp.json()["cached_models"]) == 1


class TestDeleteOllamaServer:
    async def test_delete(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "del-srv", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/ollama-servers/{server_id}")
        assert resp.status_code == 204

    async def test_delete_not_found(self, client: AsyncClient):
        resp = await client.delete("/api/ollama-servers/999")
        assert resp.status_code == 404

    async def test_delete_confirms_removal(self, client: AsyncClient):
        """After deletion, GET should return 404."""
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "confirm-del", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/ollama-servers/{server_id}")
        assert resp.status_code == 204

        get_resp = await client.get(f"/api/ollama-servers/{server_id}")
        assert get_resp.status_code == 404

    async def test_delete_blocked_by_role_assignments(self, client: AsyncClient):
        """Cannot delete a server that has active LLM role assignments."""
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "role-srv", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]

        # Create a role assignment
        await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "qwen2.5-coder:32b",
                },
            ],
        )

        # Try to delete - should fail with 409
        resp = await client.delete(f"/api/ollama-servers/{server_id}")
        assert resp.status_code == 409
        assert "role assignments" in resp.json()["detail"].lower()


class TestRefreshModels:
    async def test_refresh(self, client: AsyncClient, mock_fetch_models):
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "ref-srv", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]

        # Change the mock to return different models
        mock_fetch_models.return_value = (
            "online",
            [
                {"name": "model-a", "size": 100},
                {"name": "model-b", "size": 200},
            ],
            None,
        )

        resp = await client.post(f"/api/ollama-servers/{server_id}/refresh-models")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["cached_models"]) == 2

    async def test_refresh_not_found(self, client: AsyncClient):
        resp = await client.post("/api/ollama-servers/999/refresh-models")
        assert resp.status_code == 404

    async def test_refresh_when_server_goes_offline(self, client: AsyncClient, mock_fetch_models):
        """Refresh models when Ollama server becomes unreachable."""
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "offline-srv", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]
        assert create_resp.json()["status"] == "online"

        # Server goes offline
        mock_fetch_models.return_value = ("error", None, "Connection refused")

        resp = await client.post(f"/api/ollama-servers/{server_id}/refresh-models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert data["error_message"] == "Connection refused"
        assert data["cached_models"] is None

    async def test_refresh_updates_last_seen_at(self, client: AsyncClient, mock_fetch_models):
        """Successful refresh should update last_seen_at."""
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "seen-refresh", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]

        # Refresh with new models
        mock_fetch_models.return_value = (
            "online",
            [{"name": "new-model", "size": 500}],
            None,
        )

        resp = await client.post(f"/api/ollama-servers/{server_id}/refresh-models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "online"
        assert data["last_seen_at"] is not None
        assert len(data["cached_models"]) == 1
        assert data["cached_models"][0]["name"] == "new-model"

    async def test_refresh_replaces_all_models(self, client: AsyncClient, mock_fetch_models):
        """Refresh should completely replace cached model list."""
        # Create with one model
        mock_fetch_models.return_value = (
            "online",
            [{"name": "model-a", "size": 100}],
            None,
        )
        create_resp = await client.post(
            "/api/ollama-servers",
            json={"name": "replace-srv", "url": "http://10.0.0.1:11434"},
        )
        server_id = create_resp.json()["id"]
        assert len(create_resp.json()["cached_models"]) == 1

        # Refresh with completely different models
        mock_fetch_models.return_value = (
            "online",
            [
                {"name": "model-x", "size": 300},
                {"name": "model-y", "size": 400},
                {"name": "model-z", "size": 500},
            ],
            None,
        )
        resp = await client.post(f"/api/ollama-servers/{server_id}/refresh-models")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["cached_models"]) == 3
        model_names = {m["name"] for m in data["cached_models"]}
        assert model_names == {"model-x", "model-y", "model-z"}
