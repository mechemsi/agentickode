# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Discord notification provider."""

import httpx


class DiscordProvider:
    """Send notifications via Discord webhook."""

    async def send(self, message: str, config: dict, client: httpx.AsyncClient) -> None:
        url = config["webhook_url"]
        resp = await client.post(url, json={"content": message}, timeout=10)
        resp.raise_for_status()

    async def test(self, config: dict, client: httpx.AsyncClient) -> tuple[bool, str | None]:
        try:
            await self.send("AgenticKode test notification", config, client)
            return True, None
        except Exception as e:
            return False, str(e)
