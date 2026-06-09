# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""REST endpoints for local terminal session management."""

import asyncio
import logging
import os
import shlex
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.local_sessions import LocalTerminalSession
from backend.services.workspace.platform_user import get_platform_run_as_user
from backend.worker.broadcaster import broadcaster

logger = logging.getLogger("agentickode.api.local_terminals")
router = APIRouter(tags=["local-terminals"])


def _tmux(cmd: str, run_as_user: str | None) -> str:
    """Wrap a tmux shell command to run as ``run_as_user`` via ``runuser``.

    The tmux server is per-user, so create/send/attach/kill/has-session for a
    given session must all run as the same user. No-op when ``run_as_user`` is
    falsy (runs as the backend process user — pre-existing behaviour).
    """
    if not run_as_user:
        return cmd
    return f"runuser -l {shlex.quote(run_as_user)} -c {shlex.quote(cmd)}"


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
    agent_session_id: str | None
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
        if s.status == "active" and not await _tmux_exists(s.tmux_name, s.run_as_user):
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

    # Run the tmux session as the platform server's worker user when configured.
    run_as_user = await get_platform_run_as_user(db)
    env = {
        **os.environ,
        "TERM": "xterm-256color",
        "PATH": f"/root/.local/bin:/root/.local/share/claude/bin:{os.environ.get('PATH', '')}",
    }

    # Create tmux with a shell, then launch agent inside it.
    # Claude uses --session-id so we can --resume later.
    claude_session_id = str(uuid.uuid4())
    if body.agent_name == "claude":
        agent_launch = f"claude --permission-mode auto --session-id {claude_session_id}"
    else:
        agent_launch = body.agent_name

    proc = await asyncio.create_subprocess_shell(
        _tmux(f"tmux new-session -d -s {tmux_name} -x 120 -y 40", run_as_user),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        raise HTTPException(500, f"Failed to create tmux session: {stderr}")

    # Enable mouse scrolling and increase scrollback
    await asyncio.create_subprocess_shell(
        _tmux(
            f"tmux set-option -t {tmux_name} mouse on && "
            f"tmux set-option -t {tmux_name} history-limit 10000",
            run_as_user,
        ),
        env=env,
    )

    # Send the agent launch command into the shell
    await asyncio.create_subprocess_shell(
        _tmux(f"tmux send-keys -t {tmux_name} '{agent_launch}' Enter", run_as_user),
        env=env,
    )

    session = LocalTerminalSession(
        session_id=session_id,
        agent_name=body.agent_name,
        tmux_name=tmux_name,
        display_name=display_name,
        last_command=agent_launch,
        agent_session_id=claude_session_id if body.agent_name == "claude" else None,
        run_as_user=run_as_user,
        status="active",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info("Created local terminal session %s (%s)", session_id, tmux_name)

    # Notify office view
    await broadcaster.office_event(
        {
            "type": "agent_spawned",
            "agent": {
                "id": f"local-{session_id}",
                "agent_type": body.agent_name,
                "status": "active",
                "activity": "coding",
                "project": "",
                "phase": "chat",
                "run_id": None,
                "display_name": display_name,
            },
            "room_id": "platform",
        }
    )

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

    run_as_user = session.run_as_user

    # If tmux is already running, just mark active
    if await _tmux_exists(session.tmux_name, run_as_user):
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
        _tmux(f"tmux new-session -d -s {session.tmux_name} -x 120 -y 40", run_as_user),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        raise HTTPException(500, f"Failed to create tmux session: {stderr}")

    # Enable mouse scrolling and increase scrollback
    await asyncio.create_subprocess_shell(
        _tmux(
            f"tmux set-option -t {session.tmux_name} mouse on && "
            f"tmux set-option -t {session.tmux_name} history-limit 10000",
            run_as_user,
        ),
        env=env,
    )

    # Re-launch the agent — use --resume if we have a Claude session ID
    if session.agent_session_id and session.agent_name == "claude":
        agent_cmd = f"claude --permission-mode auto --resume {session.agent_session_id}"
    else:
        agent_cmd = session.last_command or session.agent_name
    await asyncio.create_subprocess_shell(
        _tmux(f"tmux send-keys -t {session.tmux_name} '{agent_cmd}' Enter", run_as_user),
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

    # Kill tmux (as the user that owns the session's tmux server)
    await asyncio.create_subprocess_shell(
        _tmux(f"tmux kill-session -t {session.tmux_name} 2>/dev/null || true", session.run_as_user)
    )

    await db.delete(session)
    await db.commit()

    logger.info("Deleted local terminal session %s", session_id)

    # Notify office view
    await broadcaster.office_event(
        {
            "type": "agent_left",
            "agent_id": f"local-{session_id}",
        }
    )

    return {"status": "deleted"}


async def _tmux_exists(tmux_name: str, run_as_user: str | None = None) -> bool:
    """Check if a tmux session exists (on the owning user's tmux server)."""
    proc = await asyncio.create_subprocess_shell(
        _tmux(f"tmux has-session -t {tmux_name} 2>/dev/null", run_as_user),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    return proc.returncode == 0
