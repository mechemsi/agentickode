# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for role assignments API."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def mock_fetch_models():
    """Mock Ollama API for creating test servers."""
    with patch("backend.api.ollama_servers._fetch_models") as mock:
        mock.return_value = (
            "online",
            [{"name": "qwen2.5-coder:32b", "size": 1000}],
            None,
        )
        yield mock


async def _create_ollama_server(client: AsyncClient, name: str = "gpu-01") -> int:
    resp = await client.post(
        "/api/ollama-servers",
        json={"name": name, "url": "http://10.0.0.1:11434"},
    )
    return resp.json()["id"]


async def _create_workspace_server(client: AsyncClient, name: str = "ws-01") -> int:
    resp = await client.post(
        "/api/workspace-servers",
        json={
            "name": name,
            "hostname": "10.0.0.1",
            "port": 22,
            "username": "root",
        },
    )
    return resp.json()["id"]


class TestListRoleAssignments:
    async def test_empty(self, client: AsyncClient):
        resp = await client.get("/api/role-assignments")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, client: AsyncClient):
        server_id = await _create_ollama_server(client, name="list-gpu")
        await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "qwen2.5-coder:32b",
                },
                {
                    "role": "coder",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "devstral:24b",
                },
            ],
        )
        resp = await client.get("/api/role-assignments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        roles = {r["role"] for r in data}
        assert roles == {"planner", "coder"}
        for r in data:
            assert r["ollama_server_name"] == "list-gpu"
            assert r["provider_type"] == "ollama"
            assert "created_at" in r
            assert "updated_at" in r

    async def test_legacy_llm_roles_endpoint(self, client: AsyncClient):
        """Legacy /api/llm-roles endpoint still works."""
        server_id = await _create_ollama_server(client)
        await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "model-a",
                },
            ],
        )
        resp = await client.get("/api/llm-roles")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_scope_filter(self, client: AsyncClient):
        """Scope query param filters by workspace_server_id."""
        server_id = await _create_ollama_server(client)
        ws_id = await _create_workspace_server(client)

        await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "model-a",
                },
                {
                    "role": "coder",
                    "provider_type": "agent",
                    "agent_name": "claude",
                    "workspace_server_id": ws_id,
                },
            ],
        )
        # Unscoped: should return both
        resp = await client.get("/api/role-assignments")
        assert len(resp.json()) == 2

        # Scoped to workspace server
        resp = await client.get(f"/api/role-assignments?scope_server_id={ws_id}")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["role"] == "coder"
        assert data[0]["agent_name"] == "claude"


class TestBulkUpsert:
    async def test_create_ollama_roles(self, client: AsyncClient):
        server_id = await _create_ollama_server(client)
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "qwen2.5-coder:32b",
                },
                {
                    "role": "coder",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "devstral:24b",
                },
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["role"] == "planner"
        assert data[0]["ollama_server_name"] == "gpu-01"

    async def test_create_agent_role(self, client: AsyncClient):
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "coder",
                    "provider_type": "agent",
                    "agent_name": "openhands",
                },
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["provider_type"] == "agent"
        assert data[0]["agent_name"] == "openhands"
        assert data[0]["ollama_server_id"] is None

    async def test_upsert_updates_existing(self, client: AsyncClient):
        server_id = await _create_ollama_server(client)
        await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "model-a",
                },
            ],
        )
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "model-b",
                },
            ],
        )
        assert resp.status_code == 200
        assert resp.json()[0]["model_name"] == "model-b"

        list_resp = await client.get("/api/role-assignments")
        assert len(list_resp.json()) == 1

    async def test_primary_and_fallback(self, client: AsyncClient):
        """Can create primary and fallback for same role."""
        server_id = await _create_ollama_server(client)
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "primary-model",
                    "priority": 0,
                },
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "fallback-model",
                    "priority": 1,
                },
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        priorities = {r["priority"] for r in data}
        assert priorities == {0, 1}

    async def test_all_valid_roles(self, client: AsyncClient):
        server_id = await _create_ollama_server(client)
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "m1",
                },
                {
                    "role": "coder",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "m2",
                },
                {
                    "role": "reviewer",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "m3",
                },
                {
                    "role": "fast",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "m4",
                },
            ],
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 4
        roles = {r["role"] for r in resp.json()}
        assert roles == {"planner", "coder", "reviewer", "fast"}

    async def test_empty_body(self, client: AsyncClient):
        resp = await client.put("/api/role-assignments", json=[])
        assert resp.status_code == 200
        assert resp.json() == []


class TestValidation:
    async def test_invalid_role_name(self, client: AsyncClient):
        server_id = await _create_ollama_server(client)
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "invalid_role",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "model-a",
                },
            ],
        )
        assert resp.status_code == 400

    async def test_invalid_provider_type(self, client: AsyncClient):
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "invalid",
                },
            ],
        )
        assert resp.status_code == 400

    async def test_ollama_requires_server_and_model(self, client: AsyncClient):
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                },
            ],
        )
        assert resp.status_code == 400

    async def test_agent_requires_agent_name(self, client: AsyncClient):
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "coder",
                    "provider_type": "agent",
                },
            ],
        )
        assert resp.status_code == 400

    async def test_unknown_agent_name(self, client: AsyncClient):
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "coder",
                    "provider_type": "agent",
                    "agent_name": "unknown_agent",
                },
            ],
        )
        assert resp.status_code == 400

    async def test_invalid_priority(self, client: AsyncClient):
        server_id = await _create_ollama_server(client)
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "m",
                    "priority": 5,
                },
            ],
        )
        assert resp.status_code == 400

    async def test_invalid_ollama_server_id(self, client: AsyncClient):
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": 9999,
                    "model_name": "model-a",
                },
            ],
        )
        assert resp.status_code == 400

    async def test_invalid_workspace_server_id(self, client: AsyncClient):
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "coder",
                    "provider_type": "agent",
                    "agent_name": "claude",
                    "workspace_server_id": 9999,
                },
            ],
        )
        assert resp.status_code == 400

    async def test_valid_agent_names(self, client: AsyncClient):
        """All valid agent names accepted."""
        for agent in ("claude", "codex", "opencode", "aider", "openhands"):
            resp = await client.put(
                "/api/role-assignments",
                json=[
                    {
                        "role": "coder",
                        "provider_type": "agent",
                        "agent_name": agent,
                    },
                ],
            )
            assert resp.status_code == 200, f"Agent {agent} should be valid"


class TestDeleteAssignment:
    async def test_delete_existing(self, client: AsyncClient):
        server_id = await _create_ollama_server(client)
        resp = await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "model-a",
                },
            ],
        )
        assignment_id = resp.json()[0]["id"]

        del_resp = await client.delete(f"/api/role-assignments/{assignment_id}")
        assert del_resp.status_code == 204

        list_resp = await client.get("/api/role-assignments")
        assert len(list_resp.json()) == 0

    async def test_delete_nonexistent(self, client: AsyncClient):
        resp = await client.delete("/api/role-assignments/9999")
        assert resp.status_code == 404


class TestDeleteServerWithRoles:
    async def test_delete_server_with_roles_blocked(self, client: AsyncClient):
        server_id = await _create_ollama_server(client)
        await client.put(
            "/api/role-assignments",
            json=[
                {
                    "role": "planner",
                    "provider_type": "ollama",
                    "ollama_server_id": server_id,
                    "model_name": "model-a",
                },
            ],
        )
        resp = await client.delete(f"/api/ollama-servers/{server_id}")
        assert resp.status_code == 409