# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for the Health API endpoint."""

from unittest.mock import AsyncMock, patch

from backend.models import OllamaServer


class TestHealthEndpoint:
    async def test_health_ok_with_online_ollama_servers(self, client, db_session):
        """When DB has ollama servers and they respond, status is ok."""
        server = OllamaServer(name="gpu-1", url="http://fake:11434", status="online")
        db_session.add(server)
        await db_session.commit()

        with patch("backend.api.health.get_http_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_client.get.return_value = mock_resp
            mock_client_fn.return_value = mock_client

            with patch("backend.api.health.settings") as mock_settings:
                mock_settings.openhands_url = ""

                resp = await client.get("/api/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        names = [s["name"] for s in data["services"]]
        assert "database" in names
        assert "ollama:gpu-1" in names
        assert "openhands" not in names

    async def test_health_not_configured_when_no_ollama_servers(self, client):
        """When no ollama servers in DB, show not_configured."""
        with patch("backend.api.health.settings") as mock_settings:
            mock_settings.openhands_url = ""

            resp = await client.get("/api/health")

        data = resp.json()
        assert data["status"] == "ok"
        ollama = next(s for s in data["services"] if s["name"] == "ollama")
        assert ollama["status"] == "not_configured"

    async def test_health_degraded_when_ollama_server_down(self, client, db_session):
        """When an ollama server fails health check, status is degraded."""
        server = OllamaServer(name="gpu-1", url="http://fake:11434", status="online")
        db_session.add(server)
        await db_session.commit()

        with patch("backend.api.health.get_http_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("connection refused")
            mock_client_fn.return_value = mock_client

            with patch("backend.api.health.settings") as mock_settings:
                mock_settings.openhands_url = ""

                resp = await client.get("/api/health")

        data = resp.json()
        assert data["status"] == "degraded"

    async def test_health_skips_openhands_when_not_configured(self, client):
        """When openhands_url is empty, openhands is not checked."""
        with patch("backend.api.health.settings") as mock_settings:
            mock_settings.openhands_url = ""

            resp = await client.get("/api/health")

        data = resp.json()
        names = [s["name"] for s in data["services"]]
        assert "openhands" not in names

    async def test_health_checks_openhands_when_configured(self, client):
        """When openhands_url is set, openhands is checked."""
        with patch("backend.api.health.settings") as mock_settings:
            mock_settings.openhands_url = "http://openhands:3000"

            with patch("backend.api.health.get_http_client") as mock_client_fn:
                mock_client = AsyncMock()
                mock_resp = AsyncMock()
                mock_resp.status_code = 200
                mock_client.get.return_value = mock_resp
                mock_client_fn.return_value = mock_client

                resp = await client.get("/api/health")

        data = resp.json()
        names = [s["name"] for s in data["services"]]
        assert "openhands" in names
