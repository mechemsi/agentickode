# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""REST endpoints for local terminal session management."""

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime

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


class RenameRequest(BaseModel):
    display_name: str


class SessionOut(BaseModel):
    id: int
    session_id: str
    agent_name: str
    tmux_name: str
    display_name: str | None
    last_command: str | None
    status: str
    created_at: datetime
    last_activity_at: datetime

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

    # Create tmux with a shell, then launch agent inside it.
    # Claude needs a proper shell env — direct exec as tmux command fails.
    if body.agent_name == "claude":
        agent_launch = "claude --permission-mode auto"
    else:
        agent_launch = body.agent_name

    proc = await asyncio.create_subprocess_shell(
        f"tmux new-session -d -s {tmux_name} -x 120 -y 40",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        raise HTTPException(500, f"Failed to create tmux session: {stderr}")

    # Send the agent launch command into the shell
    await asyncio.create_subprocess_shell(
        f"tmux send-keys -t {tmux_name} '{agent_launch}' Enter",
        env=env,
    )

    session = LocalTerminalSession(
        session_id=session_id,
        agent_name=body.agent_name,
        tmux_name=tmux_name,
        display_name=display_name,
        last_command=agent_launch,
        status="active",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info("Created local terminal session %s (%s)", session_id, tmux_name)
    return session


@router.post("/local-terminals/{session_id}/rename", response_model=SessionOut)
async def rename_session(
    session_id: str,
    body: RenameRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rename a local terminal session."""
    result = await db.execute(
        select(LocalTerminalSession).where(LocalTerminalSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    session.display_name = body.display_name
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/local-terminals/{session_id}/resume", response_model=SessionOut)
async def resume_local_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Resume a closed/orphaned local terminal session by re-creating its tmux."""
    result = await db.execute(
        select(LocalTerminalSession).where(LocalTerminalSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    # If tmux is already running, just mark active
    if await _tmux_exists(session.tmux_name):
        session.status = "active"
        session.last_activity_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(session)
        return session

    env = {
        **os.environ,
        "TERM": "xterm-256color",
        "PATH": f"/root/.local/bin:/root/.local/share/claude/bin:{os.environ.get('PATH', '')}",
    }

    # Re-create tmux session with the same name
    proc = await asyncio.create_subprocess_shell(
        f"tmux new-session -d -s {session.tmux_name} -x 120 -y 40",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        raise HTTPException(500, f"Failed to create tmux session: {stderr}")

    # Re-launch the agent command
    agent_cmd = session.last_command or session.agent_name
    await asyncio.create_subprocess_shell(
        f"tmux send-keys -t {session.tmux_name} '{agent_cmd}' Enter",
        env=env,
    )

    session.status = "active"
    session.closed_at = None
    session.last_activity_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(session)

    logger.info("Resumed local terminal session %s (%s)", session_id, session.tmux_name)
    return session


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
