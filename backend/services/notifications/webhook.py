# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Generic webhook notification provider."""

import httpx


class WebhookProvider:
    """Send notifications via a generic HTTP webhook."""

    async def send(self, message: str, config: dict, client: httpx.AsyncClient) -> None:
        url = config["url"]
        method = config.get("method", "POST").upper()
        headers = config.get("headers", {})
        resp = await client.request(
            method,
            url,
            json={"message": message},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()

    async def test(self, config: dict, client: httpx.AsyncClient) -> tuple[bool, str | None]:
        try:
            await self.send("AgenticKode test notification", config, client)
            return True, None
        except Exception as e:
            return False, str(e)
