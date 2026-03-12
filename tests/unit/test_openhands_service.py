# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for OpenHandsService."""

from unittest.mock import AsyncMock, MagicMock

import httpx

from backend.services.openhands_service import OpenHandsService


class TestOpenHandsService:
    def _make(self, client=None):
        client = client or AsyncMock(spec=httpx.AsyncClient)
        return OpenHandsService(client, base_url="http://oh:3000"), client

    async def test_run_agent(self):
        svc, client = self._make()
        resp = MagicMock()
        resp.json.return_value = {"files_changed": ["a.py"]}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        result = await svc.run_agent("/ws", "do stuff")
        assert result == {"files_changed": ["a.py"]}

    async def test_get_diff(self):
        svc, client = self._make()
        resp = MagicMock()
        resp.json.return_value = {"diff": "+line"}
        resp.raise_for_status = MagicMock()
        client.get.return_value = resp
        assert await svc.get_diff("/ws", "main", "feat") == "+line"

    async def test_run_tests(self):
        svc, client = self._make()
        resp = MagicMock()
        resp.json.return_value = {"success": True, "output": "ok"}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        result = await svc.run_tests("/ws")
        assert result["success"] is True

    async def test_cleanup_workspace(self):
        svc, client = self._make()
        client.post.return_value = MagicMock()
        await svc.cleanup_workspace("/ws")
        client.post.assert_called_once()

    async def test_create_branch(self):
        svc, client = self._make()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        await svc.create_branch("/ws", "feat/x", "main")
        client.post.assert_called_once()

    async def test_push_branch(self):
        svc, client = self._make()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        await svc.push_branch("/ws", "feat/x")
        client.post.assert_called_once()

    async def test_is_healthy_true(self):
        svc, client = self._make()
        client.get.return_value = MagicMock(status_code=200)
        assert await svc.is_healthy() is True

    async def test_is_healthy_false(self):
        svc, client = self._make()
        client.get.side_effect = Exception("down")
        assert await svc.is_healthy() is False