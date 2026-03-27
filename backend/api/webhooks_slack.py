# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Slack webhook endpoint for inbound commands and event subscriptions."""

import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.services.messaging.agent_relay import AgentRelay
from backend.services.messaging.command_executor import CommandExecutor
from backend.services.messaging.command_parser import parse_command

logger = logging.getLogger("agentickode.webhooks.slack")
router = APIRouter(tags=["webhooks-slack"])


def _verify_slack_signature(body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    """Verify Slack request signature."""
    if not secret:
        return True  # Skip verification if no secret configured
    if abs(time.time() - float(timestamp)) > 300:
        return False
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    computed = (
        "v0=" + hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(computed, signature)


@router.post("/webhooks/slack")
async def slack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Slack events and slash commands."""
    raw_body = await request.body()
    body = await request.json()

    # Verify signature if secret is configured
    if settings.slack_signing_secret:
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
        signature = request.headers.get("X-Slack-Signature", "")
        if not _verify_slack_signature(
            raw_body, timestamp, signature, settings.slack_signing_secret
        ):
            raise HTTPException(403, "Invalid signature")

    # Handle URL verification challenge
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    # Handle event callbacks
    if body.get("type") == "event_callback":
        event = body.get("event", {})
        event_type = event.get("type", "")

        # Ignore bot messages to prevent loops
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return {"status": "ignored"}

        if event_type == "app_mention":
            text = event.get("text", "")
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

            # Post response back to Slack (via response_url or chat.postMessage)
            # For now, return the response — in production, use Slack Web API
            logger.info("Slack command: %s -> %s", cmd.action, response[:100])
            return {"text": response}

    # Handle slash commands
    if "command" in body:
        text = body.get("text", "")
        cmd = parse_command(text)
        executor = CommandExecutor()
        response = await executor.execute(cmd, db)
        await db.commit()
        return {"response_type": "in_channel", "text": response}

    return {"status": "ok"}
