# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for the analytics API endpoint."""

import pytest


@pytest.mark.asyncio
async def test_analytics_summary_returns_200(client):
    """GET /api/analytics/summary returns 200 with valid structure."""
    resp = await client.get("/api/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "success_rate" in data
    assert "avg_duration_seconds" in data
    assert "total_runs" in data
    assert "runs_by_status" in data
    assert "avg_phase_durations" in data
    assert "agent_stats" in data
    assert "runs_over_time" in data


@pytest.mark.asyncio
async def test_analytics_summary_days_param(client):
    """days query param is validated."""
    resp = await client.get("/api/analytics/summary?days=7")
    assert resp.status_code == 200

    resp = await client.get("/api/analytics/summary?days=0")
    assert resp.status_code == 422  # ge=1 constraint