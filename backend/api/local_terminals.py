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
from backend.models import WorkspaceServer
from backend.models.local_sessions import LocalTerminalSession
from backend.services.workspace.host_bridge_service import host_bridge_from_server
from backend.services.workspace.runuser_prefix import runuser_prefix, wrap_for_user
from backend.worker.broadcaster import broadcaster

logger = logging.getLogger("agentickode.api.local_terminals")
router = APIRouter(tags=["local-terminals"])


async def _platform_worker_user(db: AsyncSession) -> str | None:
    """Look up the local platform server's configured ``worker_user``."""
    result = await db.execute(
        select(WorkspaceServer.worker_user).where(WorkspaceServer.server_type == "local").limit(1)
    )
    user = result.scalar_one_or_none()
    return user if (isinstance(user, str) and user.strip()) else None


async def _platform_server(db: AsyncSession) -> WorkspaceServer | None:
    """Return the local platform server row, if any."""
    result = await db.execute(
        select(WorkspaceServer).where(WorkspaceServer.server_type == "local").limit(1)
    )
    return result.scalar_one_or_none()


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

    # Verify active sessions still have tmux running. Use the platform
    # worker_user's tmux socket so sessions started under that user
    # are detected correctly.
    worker_user = await _platform_worker_user(db)
    prefix = await runuser_prefix(worker_user)
    verified = []
    for s in sessions:
        if s.status == "active" and not await _tmux_exists(s.tmux_name, prefix):
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

    # Prefer the host bridge if configured: tmux runs on the operator's
    # host, with their PATH, Claude install, and project folders. Fall
    # back to the legacy in-container path (with runuser wrapping for
    # ``worker_user`` if set) when no bridge is configured.
    platform = await _platform_server(db)
    bridge = host_bridge_from_server(platform) if platform else None

    if bridge is not None:
        claude_session_id = str(uuid.uuid4())
        if body.agent_name == "claude":
            agent_launch = f"claude --permission-mode auto --session-id {claude_session_id}"
        else:
            agent_launch = body.agent_name

        # Build a single shell snippet so the daemon executes it in one
        # bash -lc call. ``send-keys`` won't fire until the new-session
        # has settled, so a tiny ``sleep 0.2`` here avoids a race that
        # otherwise sends the keystrokes into a half-initialized pane.
        snippet = (
            f"tmux new-session -d -s {tmux_name} -x 120 -y 40 && "
            f"tmux set-option -t {tmux_name} mouse on && "
            f"tmux set-option -t {tmux_name} history-limit 10000 && "
            f"sleep 0.2 && "
            f"tmux send-keys -t {tmux_name} {shlex.quote(agent_launch)} Enter"
        )
        stdout, stderr, rc = await bridge.run_command(snippet, timeout=20)
        if rc != 0:
            raise HTTPException(500, f"Failed to create tmux on host: {stderr or stdout}")

        session = LocalTerminalSession(
            session_id=session_id,
            agent_name=body.agent_name,
            tmux_name=tmux_name,
            display_name=display_name,
            last_command=agent_launch,
            agent_session_id=claude_session_id if body.agent_name == "claude" else None,
            status="active",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        logger.info("Created local terminal session %s on host bridge (%s)", session_id, tmux_name)

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

    # Resolve the platform server's worker_user (if set) and compute
    # the ``runuser -l`` prefix once. Every tmux call below is wrapped
    # with this prefix so the tmux server, its shell, and the agent
    # inside all run as the worker user — not as the backend's process
    # user (typically root in Docker).
    worker_user = await _platform_worker_user(db)
    prefix = await runuser_prefix(worker_user)

    # PATH search order: when running as the worker user we want their
    # ``~/.local/bin``; otherwise fall back to root's.
    if worker_user and prefix:
        agent_path = f"/home/{worker_user}/.local/bin:/home/{worker_user}/.local/share/claude/bin"
    else:
        agent_path = "/root/.local/bin:/root/.local/share/claude/bin"
    env = {
        **os.environ,
        "TERM": "xterm-256color",
        "PATH": f"{agent_path}:{os.environ.get('PATH', '')}",
    }

    # Create tmux with a shell, then launch agent inside it.
    # Claude uses --session-id so we can --resume later.
    claude_session_id = str(uuid.uuid4())
    if body.agent_name == "claude":
        agent_launch = f"claude --permission-mode auto --session-id {claude_session_id}"
    else:
        agent_launch = body.agent_name

    new_session = wrap_for_user(f"tmux new-session -d -s {tmux_name} -x 120 -y 40", prefix)
    proc = await asyncio.create_subprocess_shell(
        new_session,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        raise HTTPException(500, f"Failed to create tmux session: {stderr}")

    # Enable mouse scrolling and increase scrollback (same user as new-session
    # so it talks to the same tmux server).
    setup_opts = wrap_for_user(
        f"tmux set-option -t {tmux_name} mouse on && "
        f"tmux set-option -t {tmux_name} history-limit 10000",
        prefix,
    )
    await asyncio.create_subprocess_shell(setup_opts, env=env)

    # Send the agent launch command into the shell.
    send_cmd = wrap_for_user(f"tmux send-keys -t {tmux_name} '{agent_launch}' Enter", prefix)
    await asyncio.create_subprocess_shell(send_cmd, env=env)

    session = LocalTerminalSession(
        session_id=session_id,
        agent_name=body.agent_name,
        tmux_name=tmux_name,
        display_name=display_name,
        last_command=agent_launch,
        agent_session_id=claude_session_id if body.agent_name == "claude" else None,
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

    worker_user = await _platform_worker_user(db)
    prefix = await runuser_prefix(worker_user)

    # If tmux is already running (under the right user), just mark active
    if await _tmux_exists(session.tmux_name, prefix):
        session.status = "active"
        session.last_activity_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(session)
        return session

    if worker_user and prefix:
        agent_path = f"/home/{worker_user}/.local/bin:/home/{worker_user}/.local/share/claude/bin"
    else:
        agent_path = "/root/.local/bin:/root/.local/share/claude/bin"
    env = {
        **os.environ,
        "TERM": "xterm-256color",
        "PATH": f"{agent_path}:{os.environ.get('PATH', '')}",
    }

    # Re-create tmux session with the same name
    new_session = wrap_for_user(f"tmux new-session -d -s {session.tmux_name} -x 120 -y 40", prefix)
    proc = await asyncio.create_subprocess_shell(
        new_session,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        raise HTTPException(500, f"Failed to create tmux session: {stderr}")

    # Enable mouse scrolling and increase scrollback
    setup_opts = wrap_for_user(
        f"tmux set-option -t {session.tmux_name} mouse on && "
        f"tmux set-option -t {session.tmux_name} history-limit 10000",
        prefix,
    )
    await asyncio.create_subprocess_shell(setup_opts, env=env)

    # Re-launch the agent — use --resume if we have a Claude session ID
    if session.agent_session_id and session.agent_name == "claude":
        agent_cmd = f"claude --permission-mode auto --resume {session.agent_session_id}"
    else:
        agent_cmd = session.last_command or session.agent_name
    send_cmd = wrap_for_user(f"tmux send-keys -t {session.tmux_name} '{agent_cmd}' Enter", prefix)
    await asyncio.create_subprocess_shell(send_cmd, env=env)

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

    # Kill tmux (as the same user who created it, so we hit the right socket)
    worker_user = await _platform_worker_user(db)
    prefix = await runuser_prefix(worker_user)
    kill_cmd = wrap_for_user(
        f"tmux kill-session -t {session.tmux_name} 2>/dev/null || true", prefix
    )
    await asyncio.create_subprocess_shell(kill_cmd)

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


async def _tmux_exists(tmux_name: str, prefix: str = "") -> bool:
    """Check if a tmux session exists.

    ``prefix`` is a :func:`runuser_prefix` result so the check hits the
    right tmux server when sessions are owned by a non-root user.
    """
    check = wrap_for_user(f"tmux has-session -t {tmux_name} 2>/dev/null", prefix)
    proc = await asyncio.create_subprocess_shell(
        check,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    return proc.returncode == 0
