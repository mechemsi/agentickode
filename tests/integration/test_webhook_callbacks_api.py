# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for Webhook Callbacks API endpoints."""

import pytest


@pytest.fixture()
async def seeded_run(client):
    """Create a project and a run so webhook callbacks have a valid FK."""
    await client.post(
        "/api/projects",
        json={
            "project_id": "proj-wh",
            "project_slug": "wh-project",
            "repo_owner": "org",
            "repo_name": "repo",
        },
    )
    resp = await client.post(
        "/api/webhooks/plane",
        json={
            "data": {
                "id": "TASK-WH",
                "project": "proj-wh",
                "name": "Webhook test",
                "labels": [{"name": "ai-task"}],
            },
        },
    )
    return resp.json()["run_id"]


class TestListWebhooks:
    async def test_list_empty(self, client, seeded_run):
        resp = await client.get(f"/api/runs/{seeded_run}/webhooks")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, client, seeded_run):
        await client.post(
            f"/api/runs/{seeded_run}/webhooks",
            json={"url": "https://hook.example.com/cb"},
        )
        resp = await client.get(f"/api/runs/{seeded_run}/webhooks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["url"] == "https://hook.example.com/cb"


class TestCreateWebhook:
    async def test_create_minimal(self, client, seeded_run):
        resp = await client.post(
            f"/api/runs/{seeded_run}/webhooks",
            json={"url": "https://hook.example.com/cb"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["run_id"] == seeded_run
        assert data["url"] == "https://hook.example.com/cb"
        assert data["events"] == []
        assert data["headers"] == {}
        assert data["active"] is True

    async def test_create_with_all_fields(self, client, seeded_run):
        resp = await client.post(
            f"/api/runs/{seeded_run}/webhooks",
            json={
                "url": "https://hook.example.com/full",
                "events": ["phase_completed", "run_completed"],
                "headers": {"Authorization": "Bearer tok"},
                "active": False,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["events"] == ["phase_completed", "run_completed"]
        assert data["headers"] == {"Authorization": "Bearer tok"}
        assert data["active"] is False


class TestUpdateWebhook:
    async def test_update_url(self, client, seeded_run):
        resp = await client.post(
            f"/api/runs/{seeded_run}/webhooks",
            json={"url": "https://old.example.com/cb"},
        )
        wh_id = resp.json()["id"]

        resp = await client.put(
            f"/api/webhooks/{wh_id}",
            json={"url": "https://new.example.com/cb"},
        )
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://new.example.com/cb"

    async def test_update_partial(self, client, seeded_run):
        resp = await client.post(
            f"/api/runs/{seeded_run}/webhooks",
            json={"url": "https://hook.example.com/cb", "active": True},
        )
        wh_id = resp.json()["id"]

        resp = await client.put(
            f"/api/webhooks/{wh_id}",
            json={"active": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False
        assert data["url"] == "https://hook.example.com/cb"

    async def test_update_nonexistent_returns_404(self, client):
        resp = await client.put(
            "/api/webhooks/999",
            json={"url": "https://x.com"},
        )
        assert resp.status_code == 404


class TestDeleteWebhook:
    async def test_delete(self, client, seeded_run):
        resp = await client.post(
            f"/api/runs/{seeded_run}/webhooks",
            json={"url": "https://hook.example.com/del"},
        )
        wh_id = resp.json()["id"]

        resp = await client.delete(f"/api/webhooks/{wh_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = await client.get(f"/api/runs/{seeded_run}/webhooks")
        assert resp.json() == []

    async def test_delete_nonexistent_returns_404(self, client):
        resp = await client.delete("/api/webhooks/999")
        assert resp.status_code == 404