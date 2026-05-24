# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Chat service — manages conversational agent sessions.

Uses one-shot-per-message invocations with --session-id / --resume
for conversation continuity. Each message spawns a separate agent
process that exits after responding.

NOTE: --resume re-ingests the full session history, which costs tokens
on each message. For cost-sensitive use, consider using the Claude Agent
SDK (Python) for in-process stateful conversations in a future iteration.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import WorkspaceServer
from backend.models.chat import ChatSession
from backend.services.chat.agent_process import (
    invoke_agent,
    invoke_agent_streaming,
    invoke_agent_via_bridge,
    is_agent_available,
)
from backend.services.workspace.host_bridge_service import host_bridge_from_server

logger = logging.getLogger("agentickode.chat.service")


async def _platform_worker_user(db: AsyncSession) -> str | None:
    """Look up the local platform server's ``worker_user``, if any."""
    stmt = (
        select(WorkspaceServer.worker_user).where(WorkspaceServer.server_type == "local").limit(1)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    return user if (isinstance(user, str) and user.strip()) else None


async def _platform_server(db: AsyncSession) -> WorkspaceServer | None:
    """Return the local platform server row, if any."""
    stmt = select(WorkspaceServer).where(WorkspaceServer.server_type == "local").limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


class ChatService:
    """Manages conversational agent sessions with persistent history."""

    async def create_session(
        self,
        db: AsyncSession,
        user_id: str = "default",
        agent_name: str = "claude",
        display_name: str | None = None,
        platform_url: str = "http://localhost:8000",
    ) -> ChatSession:
        """Create a new chat session."""
        session_id = str(uuid.uuid4())

        if not is_agent_available(agent_name):
            logger.warning("Agent %s not available locally", agent_name)

        chat = ChatSession(
            session_id=session_id,
            user_id=user_id,
            agent_name=agent_name,
            display_name=display_name or f"Chat with {agent_name}",
            status="active",
            messages=[],
            agent_session_id=session_id,
        )
        db.add(chat)
        await db.commit()

        logger.info("Created chat session %s with %s", session_id, agent_name)
        return chat

    async def send_message(
        self,
        db: AsyncSession,
        session_id: str,
        message: str,
        platform_url: str = "http://localhost:8000",
    ) -> AsyncIterator[str]:
        """Send a message and stream the agent's response.

        Each message is a separate agent invocation:
        - First message: claude -p ... --session-id {id}
        - Subsequent: claude -p ... --resume {id}
        """
        chat = await self._get_session(db, session_id)
        if not chat:
            yield "Session not found"
            return

        # Append user message
        msgs = list(chat.messages or [])
        is_first = len([m for m in msgs if m.get("role") == "user"]) == 0
        msgs.append({"role": "user", "content": message, "timestamp": _now()})
        chat.messages = msgs
        chat.last_activity_at = datetime.now(UTC)
        await db.commit()

        # Invoke agent (one-shot with session resume)
        agent_session_id = chat.agent_session_id or chat.session_id

        platform = await _platform_server(db)
        bridge = host_bridge_from_server(platform) if platform else None
        if bridge is not None:
            # Run on the host via the bridge daemon — uses the host's
            # Claude binary, host's auth, host's project folders.
            result = await invoke_agent_via_bridge(
                bridge,
                agent_name=chat.agent_name,
                message=message,
                session_id=agent_session_id,
                is_new_session=is_first,
                platform_url=platform_url,
            )
        else:
            worker_user = platform.worker_user if platform else None
            result = await invoke_agent(
                agent_name=chat.agent_name,
                message=message,
                session_id=agent_session_id,
                is_new_session=is_first,
                platform_url=platform_url,
                worker_user=worker_user,
            )

        # Append assistant response
        msgs = list(chat.messages or [])
        msgs.append(
            {
                "role": "assistant",
                "content": result.output,
                "timestamp": _now(),
                "exit_code": result.exit_code,
            }
        )
        chat.messages = msgs
        chat.last_activity_at = datetime.now(UTC)
        await db.commit()

        yield result.output

    async def send_message_streaming(
        self,
        db: AsyncSession,
        session_id: str,
        message: str,
        platform_url: str = "http://localhost:8000",
    ) -> AsyncIterator[str]:
        """Send a message and stream chunks as they arrive."""
        chat = await self._get_session(db, session_id)
        if not chat:
            yield "Session not found"
            return

        msgs = list(chat.messages or [])
        is_first = len([m for m in msgs if m.get("role") == "user"]) == 0
        msgs.append({"role": "user", "content": message, "timestamp": _now()})
        chat.messages = msgs
        chat.last_activity_at = datetime.now(UTC)
        await db.commit()

        agent_session_id = chat.agent_session_id or chat.session_id
        response_parts: list[str] = []

        platform = await _platform_server(db)
        bridge = host_bridge_from_server(platform) if platform else None
        if bridge is not None:
            # Bridge path: single shot via /run (no streaming yet — the
            # daemon only exposes /pty for streaming; chat aggregation
            # works one message at a time).
            result = await invoke_agent_via_bridge(
                bridge,
                agent_name=chat.agent_name,
                message=message,
                session_id=agent_session_id,
                is_new_session=is_first,
                platform_url=platform_url,
            )
            response_parts.append(result.output)
            yield result.output
        else:
            worker_user = platform.worker_user if platform else None
            async for chunk in invoke_agent_streaming(
                agent_name=chat.agent_name,
                message=message,
                session_id=agent_session_id,
                is_new_session=is_first,
                platform_url=platform_url,
                worker_user=worker_user,
            ):
                response_parts.append(chunk)
                yield chunk

        # Store full response
        msgs = list(chat.messages or [])
        msgs.append(
            {
                "role": "assistant",
                "content": "".join(response_parts),
                "timestamp": _now(),
            }
        )
        chat.messages = msgs
        chat.last_activity_at = datetime.now(UTC)
        await db.commit()

    async def list_sessions(self, db: AsyncSession, user_id: str = "default") -> list[ChatSession]:
        """List all sessions for a user."""
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.last_activity_at.desc())
        )
        return list(result.scalars().all())

    async def close_session(self, db: AsyncSession, session_id: str) -> None:
        """Close a session."""
        chat = await self._get_session(db, session_id)
        if chat:
            chat.status = "closed"
            await db.commit()
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
