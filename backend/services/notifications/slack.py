# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Slack notification provider."""

import httpx


def _build_blocks(message: str) -> list[dict]:
    """Convert a notification message into Slack Block Kit blocks.

    First line becomes a header block, remaining lines become a mrkdwn section.
    """
    lines = message.strip().split("\n")
    blocks: list[dict] = []
    # Header from first line (strip emoji for plain_text header limit)
    header_text = lines[0][:150]
    blocks.append({"type": "header", "text": {"type": "plain_text", "text": header_text}})
    if len(lines) > 1:
        body = "\n".join(lines[1:])
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body}})
    return blocks


class SlackProvider:
    """Send notifications via Slack incoming webhook."""

    async def send(self, message: str, config: dict, client: httpx.AsyncClient) -> None:
        url = config["webhook_url"]
        payload: dict = {"text": message}
        if config.get("use_block_kit", False):
            payload["blocks"] = _build_blocks(message)
        resp = await client.post(url, json=payload, timeout=10)
        resp.raise_for_status()

    async def test(self, config: dict, client: httpx.AsyncClient) -> tuple[bool, str | None]:
        try:
            await self.send("AutoDev test notification", config, client)
            return True, None
        except Exception as e:
            return False, str(e)