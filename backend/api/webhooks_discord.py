# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Discord webhook endpoint for slash commands and interactions."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.services.messaging.agent_relay import AgentRelay
from backend.services.messaging.command_executor import CommandExecutor
from backend.services.messaging.command_parser import parse_command

logger = logging.getLogger("agentickode.webhooks.discord")
router = APIRouter(tags=["webhooks-discord"])

# Discord interaction types
_PING = 1
_APPLICATION_COMMAND = 2


@router.post("/webhooks/discord")
async def discord_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Discord interactions (slash commands)."""
    body = await request.json()
    interaction_type = body.get("type", 0)

    # Respond to Discord ping (verification)
    if interaction_type == _PING:
        return {"type": 1}

    # Handle slash commands
    if interaction_type == _APPLICATION_COMMAND:
        data = body.get("data", {})
        command_name = data.get("name", "")
        options = data.get("options", [])

        # Extract text from options
        text_parts = [command_name]
        for opt in options:
            text_parts.append(str(opt.get("value", "")))

        text = " ".join(text_parts)
        cmd = parse_command(text)

        if cmd.action == "talk":
            relay = AgentRelay()
            session_id = cmd.args.get("session_id", "")
            message = cmd.args.get("message", "")
            response = await relay.relay_to_agent(session_id, message, db)
        else:
            executor = CommandExecutor()
            response = await executor.execute(cmd, db)
            await db.commit()

        logger.info("Discord command: %s -> %s", cmd.action, response[:100])
        return {"type": 4, "data": {"content": response}}

    return {"type": 1}
