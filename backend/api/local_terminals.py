# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""REST endpoints for local terminal session management."""

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.local_sessions import LocalTerminalSession

logger = logging.getLogger("agentickode.api.local_terminals")
router = APIRouter(tags=["local-terminals"])


class CreateSessionRequest(BaseModel):
    agent_name: str
    display_name: str | None = None


class SessionOut(BaseModel):
    id: int
    session_id: str
    agent_name: str
    tmux_name: str
    display_name: str | None
    status: str
    created_at: str
    last_activity_at: str

    model_config = {"from_attributes": True}


@router.get("/local-terminals", response_model=list[SessionOut])
async def list_local_sessions(db: AsyncSession = Depends(get_db)):
    """List all local terminal sessions (active ones first)."""
    result = await db.execute(
        select(LocalTerminalSession).order_by(
            LocalTerminalSession.status.asc(),
            LocalTerminalSession.last_activity_at.desc(),
        )
    )
    sessions = result.scalars().all()

    # Verify active sessions still have tmux running
    verified = []
    for s in sessions:
        if s.status == "active" and not await _tmux_exists(s.tmux_name):
            s.status = "closed"
        verified.append(s)
    await db.commit()
    return verified


@router.post("/local-terminals", response_model=SessionOut)
async def create_local_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new local terminal session with a tmux-backed agent."""
    session_id = uuid.uuid4().hex[:12]
    tmux_name = f"lt-{body.agent_name}-{session_id}"
    display_name = body.display_name or f"{body.agent_name} session"

    env = {
        **os.environ,
        "TERM": "xterm-256color",
        "PATH": f"/root/.local/bin:/root/.local/share/claude/bin:{os.environ.get('PATH', '')}",
    }

    # Create tmux session with agent
    import shlex

    agent_path = shlex.quote(body.agent_name)
    proc = await asyncio.create_subprocess_shell(
        f"tmux new-session -d -s {tmux_name} -x 120 -y 40 {agent_path}",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()

    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        raise HTTPException(500, f"Failed to start {body.agent_name}: {stderr}")

    session = LocalTerminalSession(
        session_id=session_id,
        agent_name=body.agent_name,
        tmux_name=tmux_name,
        display_name=display_name,
        status="active",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info("Created local terminal session %s (%s)", session_id, tmux_name)
    return session


@router.post("/local-terminals/{session_id}/rename")
async def rename_session(
    session_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Rename a local terminal session."""
    result = await db.execute(
        select(LocalTerminalSession).where(LocalTerminalSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    session.display_name = body.get("display_name", session.display_name)
    await db.commit()
    return {"status": "ok"}


@router.delete("/local-terminals/{session_id}")
async def close_local_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Close a local terminal session and kill the tmux session."""
    result = await db.execute(
        select(LocalTerminalSession).where(LocalTerminalSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    # Kill tmux
    await asyncio.create_subprocess_shell(
        f"tmux kill-session -t {session.tmux_name} 2>/dev/null || true"
    )

    from datetime import UTC, datetime

    session.status = "closed"
    session.closed_at = datetime.now(UTC)
    await db.commit()

    logger.info("Closed local terminal session %s", session_id)
    return {"status": "closed"}


async def _tmux_exists(tmux_name: str) -> bool:
    """Check if a tmux session exists."""
    proc = await asyncio.create_subprocess_shell(
        f"tmux has-session -t {tmux_name} 2>/dev/null",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    return proc.returncode == 0
