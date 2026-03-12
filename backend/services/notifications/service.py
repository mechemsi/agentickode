# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Notification service — routes messages to the correct provider."""

import logging

import httpx

from backend.models import NotificationChannel
from backend.services.notifications.discord import DiscordProvider
from backend.services.notifications.slack import SlackProvider
from backend.services.notifications.telegram import TelegramProvider
from backend.services.notifications.webhook import WebhookProvider

logger = logging.getLogger("autodev.notifications")

_PROVIDERS: dict[str, TelegramProvider | SlackProvider | DiscordProvider | WebhookProvider] = {
    "telegram": TelegramProvider(),
    "slack": SlackProvider(),
    "discord": DiscordProvider(),
    "webhook": WebhookProvider(),
}


class NotificationService:
    """Send or test notifications through configured channels."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def send(self, channel: NotificationChannel, message: str) -> None:
        provider = _PROVIDERS.get(channel.channel_type)
        if not provider:
            logger.warning("Unknown channel type: %s", channel.channel_type)
            return
        await provider.send(message, channel.config, self._client)

    async def test(self, channel: NotificationChannel) -> tuple[bool, str | None]:
        provider = _PROVIDERS.get(channel.channel_type)
        if not provider:
            return False, f"Unknown channel type: {channel.channel_type}"
        return await provider.test(channel.config, self._client)