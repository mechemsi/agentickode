# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Chat API — WebSocket and REST endpoints for conversational agent sessions."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select

from backend.database import async_session
from backend.models.chat import ChatSession
from backend.services.chat.chat_service import chat_service

router = APIRouter(tags=["chat"])


class CreateSessionRequest(BaseModel):
    agent_name: str = "claude"
    display_name: str | None = None
    user_id: str = "default"


class SendMessageRequest(BaseModel):
    message: str


class RenameRequest(BaseModel):
    name: str


@router.post("/chat/sessions")
async def create_session(req: CreateSessionRequest):
    """Create a new chat session with a local agent."""
    async with async_session() as db:
        chat = await chat_service.create_session(
            db, user_id=req.user_id, agent_name=req.agent_name, display_name=req.display_name
        )
        return _session_to_dict(chat)


@router.get("/chat/sessions")
async def list_sessions(user_id: str = "default"):
    """List all chat sessions for a user."""
    async with async_session() as db:
        sessions = await chat_service.list_sessions(db, user_id)
        return [_session_to_dict(s) for s in sessions]


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a chat session with full message history."""
    async with async_session() as db:
        result = await db.execute(select(ChatSession).where(ChatSession.session_id == session_id))
        chat = result.scalar_one_or_none()
        if not chat:
            return {"error": "Session not found"}
        return _session_to_dict(chat)


@router.post("/chat/sessions/{session_id}/message")
async def send_message(session_id: str, req: SendMessageRequest):
    """Send a message and get the agent's response."""
    async with async_session() as db:
        response_parts = []
        async for chunk in chat_service.send_message(db, session_id, req.message):
            response_parts.append(chunk)
        return {"response": "\n".join(response_parts)}


@router.post("/chat/sessions/{session_id}/rename")
async def rename_session(session_id: str, req: RenameRequest):
    """Rename a chat session."""
    async with async_session() as db:
        chat = await chat_service.rename_session(db, session_id, req.name)
        if not chat:
            return {"error": "Session not found"}
        return _session_to_dict(chat)


@router.delete("/chat/sessions/{session_id}")
async def close_session(session_id: str):
    """Close a chat session."""
    async with async_session() as db:
        await chat_service.close_session(db, session_id)
    return {"status": "closed"}


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """WebSocket for real-time streaming chat with the agent."""
    await websocket.accept()

    # Verify session exists
    async with async_session() as db:
        result = await db.execute(select(ChatSession).where(ChatSession.session_id == session_id))
        if not result.scalar_one_or_none():
            await websocket.send_json({"type": "error", "content": "Session not found"})
            await websocket.close()
            return

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "message":
                content = data.get("content", "")
                async with async_session() as db:
                    async for chunk in chat_service.send_message_streaming(db, session_id, content):
                        await websocket.send_json({"type": "chunk", "content": chunk})
                await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass


def _session_to_dict(chat) -> dict:
    return {
        "session_id": chat.session_id,
        "user_id": chat.user_id,
        "agent_name": chat.agent_name,
        "display_name": chat.display_name,
        "status": chat.status,
        "messages": chat.messages or [],
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "last_activity_at": chat.last_activity_at.isoformat() if chat.last_activity_at else None,
    }
