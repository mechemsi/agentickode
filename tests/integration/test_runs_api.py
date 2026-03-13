# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for the Runs API endpoints."""

import pytest


@pytest.fixture()
async def seeded_project(client):
    """Create a project so task runs have a valid FK."""
    await client.post(
        "/api/projects",
        json={
            "project_id": "proj-runs",
            "project_slug": "runs-project",
            "repo_owner": "org",
            "repo_name": "repo",
        },
    )
    return "proj-runs"


class TestRunsList:
    async def test_list_empty(self, client):
        resp = await client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["offset"] == 0
        assert data["limit"] == 50

    async def test_list_with_filters(self, client):
        resp = await client.get("/api/runs?status=pending&limit=10&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    async def test_list_paginated_response_format(self, client, seeded_project):
        # Create a run first
        await client.post(
            "/api/runs",
            json={"project_id": seeded_project, "title": "Paginated test"},
        )
        resp = await client.get("/api/runs?limit=5&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["limit"] == 5
        assert data["offset"] == 0
        assert len(data["items"]) >= 1

    async def test_search_param(self, client, seeded_project):
        await client.post(
            "/api/runs",
            json={"project_id": seeded_project, "title": "UniqueSearchTerm42"},
        )
        resp = await client.get("/api/runs?search=UniqueSearchTerm42")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any("UniqueSearchTerm42" in item["title"] for item in data["items"])

    async def test_sort_params(self, client):
        resp = await client.get("/api/runs?sort_by=title&sort_order=asc")
        assert resp.status_code == 200


class TestRunDetail:
    async def test_get_nonexistent_returns_404(self, client):
        resp = await client.get("/api/runs/999")
        assert resp.status_code == 404


class TestRunActions:
    async def test_approve_nonexistent_returns_404(self, client):
        resp = await client.post("/api/runs/999/approve")
        assert resp.status_code == 404

    async def test_reject_nonexistent_returns_404(self, client):
        resp = await client.post("/api/runs/999/reject", json={"reason": "bad"})
        assert resp.status_code == 404

    async def test_retry_nonexistent_returns_404(self, client):
        resp = await client.post("/api/runs/999/retry")
        assert resp.status_code == 404

    async def test_cancel_nonexistent_returns_404(self, client):
        resp = await client.post("/api/runs/999/cancel")
        assert resp.status_code == 404


class TestStats:
    async def test_stats_empty(self, client):
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 0
        assert data["pending"] == 0
        assert data["running"] == 0


class TestWebhookToRunFlow:
    """Integration: webhook creates a run, run appears in list and detail."""

    async def test_plane_webhook_creates_run(self, client, seeded_project):
        payload = {
            "event": "issue.created",
            "data": {
                "id": "TASK-100",
                "project": seeded_project,
                "name": "Fix auth bug",
                "description": "The login page is broken",
                "labels": [{"name": "ai-task"}],
                "workspace_detail": {"slug": "my-workspace"},
                "state_detail": {"group": "backlog"},
            },
        }
        resp = await client.post("/api/webhooks/plane", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        run_id = data["run_id"]

        # Verify run appears in list
        resp = await client.get("/api/runs")
        runs = resp.json()["items"]
        assert any(r["id"] == run_id for r in runs)

        # Verify run detail
        resp = await client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["title"] == "Fix auth bug"
        assert detail["task_source"] == "plane"
        assert detail["branch_name"] == "feature/ai-TASK-100"

    async def test_plane_webhook_ignores_non_ai_task(self, client, seeded_project):
        payload = {
            "data": {
                "id": "TASK-200",
                "project": seeded_project,
                "name": "Normal task",
                "labels": [{"name": "bug"}],
            },
        }
        resp = await client.post("/api/webhooks/plane", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    async def test_github_webhook_creates_run(self, client, seeded_project):
        # First update the project to have github git_provider
        await client.put(
            f"/api/projects/{seeded_project}",
            json={"git_provider": "github", "repo_owner": "org", "repo_name": "repo"},
        )
        payload = {
            "action": "labeled",
            "issue": {
                "number": 42,
                "title": "Add feature X",
                "body": "We need feature X",
                "labels": [{"name": "ai-task"}],
            },
            "repository": {"full_name": "org/repo"},
        }
        resp = await client.post("/api/webhooks/github", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"

    async def test_github_webhook_ignores_wrong_action(self, client):
        payload = {
            "action": "closed",
            "issue": {"labels": [{"name": "ai-task"}]},
        }
        resp = await client.post("/api/webhooks/github", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


class TestRunLifecycle:
    """Integration: create run via webhook, then approve/reject/cancel/retry."""

    async def _create_run(self, client, seeded_project) -> int:
        payload = {
            "data": {
                "id": "TASK-LC",
                "project": seeded_project,
                "name": "Lifecycle test",
                "labels": [{"name": "ai-task"}],
            },
        }
        resp = await client.post("/api/webhooks/plane", json=payload)
        return resp.json()["run_id"]

    async def test_cancel_pending_run(self, client, seeded_project):
        run_id = await self._create_run(client, seeded_project)
        resp = await client.post(f"/api/runs/{run_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_cannot_approve_pending_run(self, client, seeded_project):
        run_id = await self._create_run(client, seeded_project)
        resp = await client.post(f"/api/runs/{run_id}/approve")
        assert resp.status_code == 400

    async def test_retry_after_cancel(self, client, seeded_project):
        run_id = await self._create_run(client, seeded_project)
        await client.post(f"/api/runs/{run_id}/cancel")
        resp = await client.post(f"/api/runs/{run_id}/retry")
        assert resp.status_code == 200
        assert resp.json()["status"] == "retried"

    async def test_cannot_retry_pending_run(self, client, seeded_project):
        run_id = await self._create_run(client, seeded_project)
        resp = await client.post(f"/api/runs/{run_id}/retry")
        assert resp.status_code == 400


class TestPhaseEndpoints:
    """Integration tests for phase execution endpoints."""

    async def _create_run(self, client, seeded_project) -> int:
        payload = {
            "data": {
                "id": "TASK-PE",
                "project": seeded_project,
                "name": "Phase test",
                "labels": [{"name": "ai-task"}],
            },
        }
        resp = await client.post("/api/webhooks/plane", json=payload)
        return resp.json()["run_id"]

    async def test_list_phases_empty(self, client, seeded_project):
        run_id = await self._create_run(client, seeded_project)
        resp = await client.get(f"/api/runs/{run_id}/phases")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_phases_404(self, client):
        resp = await client.get("/api/runs/999/phases")
        assert resp.status_code == 404

    async def test_advance_nonexistent_run(self, client):
        resp = await client.post("/api/runs/999/phases/init/advance")
        assert resp.status_code == 404

    async def test_advance_nonexistent_phase(self, client, seeded_project):
        run_id = await self._create_run(client, seeded_project)
        resp = await client.post(f"/api/runs/{run_id}/phases/nonexistent/advance")
        assert resp.status_code == 404


class TestPlanReview:
    """Integration tests for POST /runs/{id}/plan-review."""

    async def test_plan_review_nonexistent_run_404(self, client):
        resp = await client.post(
            "/api/runs/999/plan-review",
            json={"action": "approve"},
        )
        assert resp.status_code == 404

    async def test_plan_review_wrong_status_400(self, client, seeded_project):
        """Plan review only works when run is waiting_for_trigger."""
        resp = await client.post(
            "/api/runs",
            json={"project_id": seeded_project, "title": "PR test"},
        )
        run_id = resp.json()["id"]
        resp = await client.post(
            f"/api/runs/{run_id}/plan-review",
            json={"action": "approve"},
        )
        assert resp.status_code == 400
        assert "waiting_for_trigger" in resp.json()["detail"]
