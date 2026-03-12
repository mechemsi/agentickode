# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for OllamaService."""

from unittest.mock import AsyncMock, MagicMock

import httpx

from backend.services.ollama_service import OllamaResult, OllamaService


class TestOllamaService:
    def _make(self, client=None):
        client = client or AsyncMock(spec=httpx.AsyncClient)
        return OllamaService(client, base_url="http://ollama:11434"), client

    async def test_generate_returns_ollama_result(self):
        svc, client = self._make()
        resp = MagicMock()
        resp.json.return_value = {
            "response": "Hello world",
            "prompt_eval_count": 42,
            "eval_count": 18,
            "total_duration": 500_000_000,
        }
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        result = await svc.generate("prompt", model="test-model")
        assert isinstance(result, OllamaResult)
        assert result.text == "Hello world"
        assert result.prompt_tokens == 42
        assert result.completion_tokens == 18
        assert result.total_duration_ns == 500_000_000
        client.post.assert_called_once()

    async def test_generate_missing_token_fields(self):
        svc, client = self._make()
        resp = MagicMock()
        resp.json.return_value = {"response": "hi"}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        result = await svc.generate("prompt")
        assert result.text == "hi"
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_duration_ns == 0

    async def test_generate_empty_response(self):
        svc, client = self._make()
        resp = MagicMock()
        resp.json.return_value = {}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        result = await svc.generate("prompt")
        assert result.text == ""

    async def test_chat_returns_ollama_result(self):
        svc, client = self._make()
        resp = MagicMock()
        resp.json.return_value = {
            "message": {"content": "Chat reply"},
            "prompt_eval_count": 100,
            "eval_count": 50,
            "total_duration": 1_000_000_000,
        }
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        result = await svc.chat("system", "user", model="test-model")
        assert isinstance(result, OllamaResult)
        assert result.text == "Chat reply"
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50

    async def test_is_healthy_true(self):
        svc, client = self._make()
        client.get.return_value = MagicMock(status_code=200)
        assert await svc.is_healthy() is True

    async def test_is_healthy_false_on_error(self):
        svc, client = self._make()
        client.get.side_effect = Exception("timeout")
        assert await svc.is_healthy() is False

    async def test_is_healthy_false_on_non_200(self):
        svc, client = self._make()
        client.get.return_value = MagicMock(status_code=500)
        assert await svc.is_healthy() is False