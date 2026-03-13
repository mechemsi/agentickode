# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for notification providers."""

from unittest.mock import AsyncMock, MagicMock

from backend.services.notifications.discord import DiscordProvider
from backend.services.notifications.slack import SlackProvider
from backend.services.notifications.telegram import TelegramProvider
from backend.services.notifications.webhook import WebhookProvider


def _mock_client(status_code: int = 200):
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    client.post.return_value = resp
    client.request.return_value = resp
    return client


class TestTelegramProvider:
    async def test_send_calls_api(self):
        client = _mock_client()
        provider = TelegramProvider()
        config = {"bot_token": "123:ABC", "chat_id": "-100"}
        await provider.send("Hello", config, client)
        client.post.assert_called_once()
        url = client.post.call_args[0][0]
        assert "123:ABC" in url
        assert "sendMessage" in url

    async def test_test_returns_success(self):
        client = _mock_client()
        provider = TelegramProvider()
        config = {"bot_token": "123:ABC", "chat_id": "-100"}
        ok, err = await provider.test(config, client)
        assert ok is True
        assert err is None

    async def test_test_returns_error_on_failure(self):
        client = _mock_client()
        client.post.side_effect = Exception("connection error")
        provider = TelegramProvider()
        ok, err = await provider.test({"bot_token": "x", "chat_id": "y"}, client)
        assert ok is False
        assert "connection error" in err


class TestSlackProvider:
    async def test_send_posts_to_webhook(self):
        client = _mock_client()
        provider = SlackProvider()
        config = {"webhook_url": "https://hooks.slack.com/test"}
        await provider.send("Hello", config, client)
        client.post.assert_called_once()
        assert client.post.call_args[0][0] == "https://hooks.slack.com/test"

    async def test_send_without_block_kit(self):
        client = _mock_client()
        provider = SlackProvider()
        config = {"webhook_url": "https://hooks.slack.com/test"}
        await provider.send("Hello\nWorld", config, client)
        payload = client.post.call_args[1]["json"]
        assert payload["text"] == "Hello\nWorld"
        assert "blocks" not in payload

    async def test_send_with_block_kit(self):
        client = _mock_client()
        provider = SlackProvider()
        config = {"webhook_url": "https://hooks.slack.com/test", "use_block_kit": True}
        await provider.send("Header Line\nDetail line 1\nDetail line 2", config, client)
        payload = client.post.call_args[1]["json"]
        assert "blocks" in payload
        blocks = payload["blocks"]
        assert blocks[0]["type"] == "header"
        assert blocks[0]["text"]["text"] == "Header Line"
        assert blocks[1]["type"] == "section"
        assert "Detail line 1" in blocks[1]["text"]["text"]

    async def test_test_returns_success(self):
        client = _mock_client()
        provider = SlackProvider()
        ok, err = await provider.test({"webhook_url": "https://test"}, client)
        assert ok is True
        assert err is None


class TestDiscordProvider:
    async def test_send_posts_content(self):
        client = _mock_client()
        provider = DiscordProvider()
        config = {"webhook_url": "https://discord.com/api/webhooks/test"}
        await provider.send("Hello", config, client)
        client.post.assert_called_once()
        body = client.post.call_args[1]["json"]
        assert body["content"] == "Hello"

    async def test_test_returns_error(self):
        client = _mock_client()
        client.post.side_effect = Exception("forbidden")
        provider = DiscordProvider()
        ok, err = await provider.test({"webhook_url": "https://test"}, client)
        assert ok is False
        assert "forbidden" in err


class TestWebhookProvider:
    async def test_send_uses_custom_method_and_headers(self):
        client = _mock_client()
        provider = WebhookProvider()
        config = {
            "url": "https://example.com/hook",
            "method": "PUT",
            "headers": {"Authorization": "Bearer xyz"},
        }
        await provider.send("Hello", config, client)
        client.request.assert_called_once()
        call_kwargs = client.request.call_args
        assert call_kwargs[0][0] == "PUT"
        assert call_kwargs[0][1] == "https://example.com/hook"
        assert call_kwargs[1]["headers"]["Authorization"] == "Bearer xyz"

    async def test_send_defaults_to_post(self):
        client = _mock_client()
        provider = WebhookProvider()
        config = {"url": "https://example.com/hook"}
        await provider.send("Hi", config, client)
        assert client.request.call_args[0][0] == "POST"

    async def test_test_returns_success(self):
        client = _mock_client()
        provider = WebhookProvider()
        ok, err = await provider.test({"url": "https://test"}, client)
        assert ok is True
        assert err is None
