# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI session management endpoints."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.sessions import CliSession
from backend.repositories.session_repo import CliSessionRepository
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas.sessions import (
    CliSessionCreate,
    CliSessionOut,
    SessionCaptureResponse,
    SessionSendRequest,
    SessionSendResponse,
)
from backend.services.workspace.session_service import SessionService
from backend.services.workspace.ssh_service import SSHService

router = APIRouter(tags=["sessions"])


class SessionRenameRequest(BaseModel):
    display_name: str


def _session_to_out(s: CliSession, server_name: str | None = None) -> CliSessionOut:
    return CliSessionOut(
        id=s.id,
        session_id=s.session_id,
        workspace_server_id=s.workspace_server_id,
        server_name=server_name,
        project_id=s.project_id,
        task_run_id=s.task_run_id,
        agent_name=s.agent_name,
        user_context=s.user_context,
        workspace_path=s.workspace_path,
        display_name=s.display_name,
        tmux_session=s.tmux_session,
        status=s.status,
        remote_control_enabled=s.remote_control_enabled,
        started_at=s.started_at,
        last_activity_at=s.last_activity_at,
        closed_at=s.closed_at,
    )


def _build_session_service(server, user: str | None = None) -> SessionService:
    ssh = SSHService.for_server(server)
    return SessionService(ssh, user=user)


@router.post("/sessions", response_model=CliSessionOut)
async def create_session(body: CliSessionCreate, db: AsyncSession = Depends(get_db)):
    """Create a new persistent CLI session."""
    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(body.workspace_server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Workspace server not found")

    session_id = str(uuid4())
    workspace_path = body.workspace_path or server.workspace_root
    svc = _build_session_service(server, user=body.user_context)

    result = await svc.create_session(
        session_id=session_id,
        agent_name=body.agent_name,
        user_context=body.user_context,
        workspace_path=workspace_path,
        tmux_name=None,
    )

    cli_session = CliSession(
        session_id=session_id,
        workspace_server_id=body.workspace_server_id,
        project_id=body.project_id,
        agent_name=body.agent_name,
        user_context=body.user_context,
        workspace_path=body.workspace_path,
        display_name=body.display_name or f"{body.agent_name}-{session_id[:8]}",
        tmux_session=result["tmux_session"],
        pid=result["pid"],
        status="active",
        remote_control_enabled=result["remote_control_enabled"],
    )

    repo = CliSessionRepository(db)
    await repo.create(cli_session)
    await db.commit()
    await db.refresh(cli_session)

    return _session_to_out(cli_session, server_name=server.name)


@router.get("/sessions", response_model=list[CliSessionOut])
async def list_sessions(
    server_id: int | None = None,
    project_id: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List sessions, optionally filtered."""
    repo = CliSessionRepository(db)
    if status and status == "closed":
        # For closed, list by server with include_closed
        if server_id:
            sessions = await repo.list_by_server(server_id, include_closed=True)
        else:
            sessions = await repo.list_active(server_id=server_id, project_id=project_id)
    else:
        sessions = await repo.list_active(server_id=server_id, project_id=project_id)

    server_repo = WorkspaceServerRepository(db)
    results = []
    for s in sessions:
        server = await server_repo.get_by_id(s.workspace_server_id)
        server_name = server.name if server else None
        results.append(_session_to_out(s, server_name=server_name))
    return results


@router.get("/sessions/{session_id}", response_model=CliSessionOut)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Get session detail by integer ID."""
    repo = CliSessionRepository(db)
    s = await repo.get_by_id(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(s.workspace_server_id)
    server_name = server.name if server else None
    return _session_to_out(s, server_name=server_name)


@router.post("/sessions/{session_id}/rename", response_model=CliSessionOut)
async def rename_session(
    session_id: int, body: SessionRenameRequest, db: AsyncSession = Depends(get_db)
):
    """Rename a CLI session."""
    repo = CliSessionRepository(db)
    s = await repo.get_by_id(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    s.display_name = body.display_name
    await db.commit()
    await db.refresh(s)

    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(s.workspace_server_id)
    server_name = server.name if server else None
    return _session_to_out(s, server_name=server_name)


@router.delete("/sessions/{session_id}")
async def close_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Kill tmux session and mark closed."""
    repo = CliSessionRepository(db)
    s = await repo.get_by_id(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(s.workspace_server_id)
    if server:
        svc = _build_session_service(server, user=s.user_context)
        await svc.kill_session(s.tmux_session)

    s.status = "closed"
    s.closed_at = datetime.now(UTC)
    await db.commit()
    return {"detail": "Session closed"}


@router.post("/sessions/{session_id}/send", response_model=SessionSendResponse)
async def send_to_session(
    session_id: int, body: SessionSendRequest, db: AsyncSession = Depends(get_db)
):
    """Send a command to the session."""
    repo = CliSessionRepository(db)
    s = await repo.get_by_id(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s.status not in ("active", "idle"):
        raise HTTPException(status_code=400, detail=f"Session is {s.status}, cannot send")

    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(s.workspace_server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Workspace server not found")

    svc = _build_session_service(server, user=s.user_context)
    output = await svc.send_command(s.tmux_session, body.message)

    s.last_activity_at = datetime.now(UTC)
    await db.commit()

    return SessionSendResponse(success=True, output=output)


@router.get("/sessions/{session_id}/capture", response_model=SessionCaptureResponse)
async def capture_session(session_id: int, lines: int = 50, db: AsyncSession = Depends(get_db)):
    """Capture current tmux pane content."""
    repo = CliSessionRepository(db)
    s = await repo.get_by_id(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(s.workspace_server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Workspace server not found")

    svc = _build_session_service(server, user=s.user_context)
    output = await svc.capture_output(s.tmux_session, lines=lines)

    return SessionCaptureResponse(output=output, lines=lines)


@router.get("/workspace-servers/{server_id}/sessions", response_model=list[CliSessionOut])
async def list_server_sessions(server_id: int, db: AsyncSession = Depends(get_db)):
    """List all active sessions on a server."""
    server_repo = WorkspaceServerRepository(db)
    server = await server_repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Workspace server not found")

    repo = CliSessionRepository(db)
    sessions = await repo.list_by_server(server_id)
    return [_session_to_out(s, server_name=server.name) for s in sessions]
