# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Telegram notification provider."""

import httpx


class TelegramProvider:
    """Send notifications via Telegram Bot API."""

    async def send(self, message: str, config: dict, client: httpx.AsyncClient) -> None:
        token = config["bot_token"]
        chat_id = config["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = await client.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()

    async def test(self, config: dict, client: httpx.AsyncClient) -> tuple[bool, str | None]:
        try:
            await self.send("AgenticKode test notification", config, client)
            return True, None
        except Exception as e:
            return False, str(e)
