# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Chat service — manages conversational agent sessions."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.chat import ChatSession
from backend.services.chat.agent_process import AgentProcess, spawn_agent

logger = logging.getLogger("agentickode.chat.service")


class ChatService:
    """Manages conversational agent sessions with persistent history."""

    def __init__(self):
        self._active: dict[str, AgentProcess] = {}

    async def create_session(
        self,
        db: AsyncSession,
        user_id: str = "default",
        agent_name: str = "claude",
        display_name: str | None = None,
        platform_url: str = "http://localhost:8000",
    ) -> ChatSession:
        """Create a new chat session and spawn a local agent.

        Returns the ChatSession DB record.
        """
        session_id = str(uuid.uuid4())

        chat = ChatSession(
            session_id=session_id,
            user_id=user_id,
            agent_name=agent_name,
            display_name=display_name or f"Chat with {agent_name}",
            status="active",
            messages=[],
        )
        db.add(chat)
        await db.commit()

        # Spawn agent process
        try:
            proc = await spawn_agent(agent_name, platform_url)
            self._active[session_id] = proc
            logger.info("Created chat session %s with %s", session_id, agent_name)
        except (ValueError, FileNotFoundError) as exc:
            chat.status = "error"
            chat.messages = [{"role": "system", "content": str(exc), "timestamp": _now()}]
            await db.commit()
            logger.error("Failed to spawn %s: %s", agent_name, exc)

        return chat

    async def send_message(
        self,
        db: AsyncSession,
        session_id: str,
        message: str,
    ) -> AsyncIterator[str]:
        """Send a message and stream the agent's response.

        Yields response chunks as they arrive.
        """
        chat = await self._get_session(db, session_id)
        if not chat:
            yield json.dumps({"error": "Session not found"})
            return

        # Append user message
        msgs = list(chat.messages or [])
        msgs.append({"role": "user", "content": message, "timestamp": _now()})
        chat.messages = msgs
        chat.last_activity_at = datetime.now(UTC)
        await db.commit()

        # Get or reconnect agent process
        proc = self._active.get(session_id)
        if not proc or not proc.alive:
            try:
                proc = await spawn_agent(chat.agent_name)
                self._active[session_id] = proc
            except (ValueError, FileNotFoundError) as exc:
                yield json.dumps({"error": str(exc)})
                return

        # Send message and stream response
        await proc.send(message)
        response = await proc.read_output(timeout=60.0)

        # Append assistant response
        msgs = list(chat.messages or [])
        msgs.append({"role": "assistant", "content": response, "timestamp": _now()})
        chat.messages = msgs
        chat.last_activity_at = datetime.now(UTC)
        await db.commit()

        yield response

    async def list_sessions(self, db: AsyncSession, user_id: str = "default") -> list[ChatSession]:
        """List all sessions for a user."""
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.last_activity_at.desc())
        )
        return list(result.scalars().all())

    async def resume_session(
        self,
        db: AsyncSession,
        session_id: str,
        platform_url: str = "http://localhost:8000",
    ) -> ChatSession | None:
        """Resume a persistent session — respawn agent if needed."""
        chat = await self._get_session(db, session_id)
        if not chat:
            return None

        chat.status = "active"
        chat.last_activity_at = datetime.now(UTC)
        await db.commit()

        # Respawn agent if not running
        if session_id not in self._active or not self._active[session_id].alive:
            try:
                proc = await spawn_agent(chat.agent_name, platform_url)
                self._active[session_id] = proc
            except (ValueError, FileNotFoundError):
                logger.warning("Could not respawn agent for session %s", session_id)

        return chat

    async def close_session(self, db: AsyncSession, session_id: str) -> None:
        """Close a session and clean up the agent process."""
        chat = await self._get_session(db, session_id)
        if chat:
            chat.status = "closed"
            await db.commit()

        proc = self._active.pop(session_id, None)
        if proc:
            await proc.kill()
            logger.info("Closed chat session %s", session_id)

    async def rename_session(
        self, db: AsyncSession, session_id: str, name: str
    ) -> ChatSession | None:
        """Rename a chat session."""
        chat = await self._get_session(db, session_id)
        if chat:
            chat.display_name = name
            await db.commit()
        return chat

    async def _get_session(self, db: AsyncSession, session_id: str) -> ChatSession | None:
        result = await db.execute(select(ChatSession).where(ChatSession.session_id == session_id))
        return result.scalar_one_or_none()


# Singleton
chat_service = ChatService()


def _now() -> str:
    return datetime.now(UTC).isoformat()
