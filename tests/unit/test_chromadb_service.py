# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for ChromaDBService."""

import logging
from unittest.mock import AsyncMock, MagicMock

import httpx

from backend.services.chromadb_service import ChromaDBService


class TestChromaDBService:
    def _make(self, client=None):
        client = client or AsyncMock(spec=httpx.AsyncClient)
        return ChromaDBService(client, base_url="http://chroma:8000", token="tok"), client

    async def test_query_success(self):
        svc, client = self._make()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"documents": [["doc1", "doc2"]]}
        client.post.return_value = resp
        result = await svc.query_project_context("proj-1", ["query"])
        assert result == ["doc1", "doc2"]

    async def test_query_returns_empty_on_error(self):
        svc, client = self._make()
        client.post.side_effect = Exception("connection refused")
        result = await svc.query_project_context("proj-1", ["query"])
        assert result == []

    async def test_query_returns_empty_on_non_200(self):
        svc, client = self._make()
        resp = MagicMock(status_code=404)
        client.post.return_value = resp
        result = await svc.query_project_context("proj-1", ["query"])
        assert result == []

    async def test_query_logs_warning_on_exception(self, caplog):
        svc, client = self._make()
        client.post.side_effect = RuntimeError("boom")
        with caplog.at_level(logging.WARNING, logger="agentickode.chromadb"):
            await svc.query_project_context("proj-1", ["query"])
        assert "ChromaDB query failed for project proj-1" in caplog.text

    async def test_query_logs_warning_on_non_200(self, caplog):
        svc, client = self._make()
        resp = MagicMock(status_code=500)
        client.post.return_value = resp
        with caplog.at_level(logging.WARNING, logger="agentickode.chromadb"):
            await svc.query_project_context("proj-1", ["query"])
        assert "ChromaDB returned 500 for project proj-1" in caplog.text
