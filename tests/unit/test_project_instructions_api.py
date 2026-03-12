# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for project instructions and secrets API endpoints."""

import pytest
from httpx import AsyncClient

from backend.models import ProjectConfig


@pytest.fixture()
async def project(db_session):
    """Create a test project."""
    p = ProjectConfig(
        project_id="test-proj",
        project_slug="test",
        repo_owner="org",
        repo_name="repo",
        default_branch="main",
        task_source="plane",
        git_provider="gitea",
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_list_instructions_empty(client: AsyncClient, project):
    resp = await client.get("/api/projects/test-proj/instructions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_upsert_global_instruction(client: AsyncClient, project):
    resp = await client.put(
        "/api/projects/test-proj/instructions",
        json={"content": "Always run tests before commit"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["phase_name"] == "__global__"
    assert data["content"] == "Always run tests before commit"
    assert data["is_active"] is True

    # Update same instruction
    resp2 = await client.put(
        "/api/projects/test-proj/instructions",
        json={"content": "Updated instructions"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["content"] == "Updated instructions"
    assert resp2.json()["id"] == data["id"]  # Same row, updated


@pytest.mark.asyncio
async def test_upsert_phase_instruction(client: AsyncClient, project):
    resp = await client.put(
        "/api/projects/test-proj/instructions/coding",
        json={"content": "Use TDD approach"},
    )
    assert resp.status_code == 200
    assert resp.json()["phase_name"] == "coding"


@pytest.mark.asyncio
async def test_invalid_phase_rejected(client: AsyncClient, project):
    resp = await client.put(
        "/api/projects/test-proj/instructions/invalid_phase",
        json={"content": "nope"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_instruction(client: AsyncClient, project):
    await client.put(
        "/api/projects/test-proj/instructions/planning",
        json={"content": "Plan carefully"},
    )
    resp = await client.delete("/api/projects/test-proj/instructions/planning")
    assert resp.status_code == 204

    # Verify gone
    resp2 = await client.get("/api/projects/test-proj/instructions")
    phases = [i["phase_name"] for i in resp2.json()]
    assert "planning" not in phases


@pytest.mark.asyncio
async def test_delete_nonexistent_instruction(client: AsyncClient, project):
    resp = await client.delete("/api/projects/test-proj/instructions/coding")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_version_created_on_upsert(client: AsyncClient, project):
    await client.put(
        "/api/projects/test-proj/instructions",
        json={"content": "v1"},
    )
    await client.put(
        "/api/projects/test-proj/instructions",
        json={"content": "v2"},
    )

    resp = await client.get("/api/projects/test-proj/instructions/versions")
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) == 2
    contents = [v["content"] for v in versions]
    assert "v1" in contents
    assert "v2" in contents


@pytest.mark.asyncio
async def test_create_secret(client: AsyncClient, project):
    resp = await client.post(
        "/api/projects/test-proj/secrets",
        json={"name": "API_KEY", "value": "secret123", "inject_as": "env_var"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "API_KEY"
    assert data["inject_as"] == "env_var"
    # Value MUST NOT be in response
    assert "value" not in data
    assert "encrypted_value" not in data


@pytest.mark.asyncio
async def test_list_secrets(client: AsyncClient, project):
    await client.post(
        "/api/projects/test-proj/secrets",
        json={"name": "KEY1", "value": "val1", "inject_as": "env_var"},
    )
    await client.post(
        "/api/projects/test-proj/secrets",
        json={"name": "KEY2", "value": "val2", "inject_as": "prompt"},
    )

    resp = await client.get("/api/projects/test-proj/secrets")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_update_secret(client: AsyncClient, project):
    create_resp = await client.post(
        "/api/projects/test-proj/secrets",
        json={"name": "MY_SECRET", "value": "old_val", "inject_as": "env_var"},
    )
    secret_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/projects/test-proj/secrets/{secret_id}",
        json={"inject_as": "prompt"},
    )
    assert resp.status_code == 200
    assert resp.json()["inject_as"] == "prompt"


@pytest.mark.asyncio
async def test_delete_secret(client: AsyncClient, project):
    create_resp = await client.post(
        "/api/projects/test-proj/secrets",
        json={"name": "TEMP", "value": "x", "inject_as": "env_var"},
    )
    secret_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/projects/test-proj/secrets/{secret_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_prompt_preview(client: AsyncClient, project):
    await client.put(
        "/api/projects/test-proj/instructions",
        json={"content": "Global instruction content"},
    )
    await client.put(
        "/api/projects/test-proj/instructions/coding",
        json={"content": "Coding-specific content"},
    )

    resp = await client.post(
        "/api/projects/test-proj/instructions/preview",
        json={"phase_name": "coding"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "Global instruction content" in data["system_prompt_section"]
    assert "Coding-specific content" in data["system_prompt_section"]