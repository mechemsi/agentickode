# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""WebSocket endpoint for the 8-bit Agent Office live view."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.database import async_session
from backend.models import CliSession, TaskRun, WorkspaceServer
from backend.models.local_sessions import LocalTerminalSession
from backend.worker.broadcaster import broadcaster

logger = logging.getLogger("agentickode.ws_office")
router = APIRouter()

# Phase name → office activity mapping
_PHASE_ACTIVITY = {
    "workspace_setup": "starting",
    "init": "starting",
    "planning": "planning",
    "coding": "coding",
    "testing": "testing",
    "reviewing": "reviewing",
    "approval": "idle",
    "finalization": "coding",
}


def _run_to_agent(run: TaskRun) -> dict | None:
    """Convert a running TaskRun to an office agent dict."""
    if run.status not in ("running", "pending"):
        return None
    phase = str(run.current_phase or "init")
    activity = _PHASE_ACTIVITY.get(phase, "coding")
    return {
        "id": f"run-{run.id}",
        "agent_type": run.agent_name or "generic",
        "room_id": run.workspace_server_id or "platform",
        "desk": None,
        "status": "active" if run.status == "running" else "starting",
        "activity": activity,
        "project": run.project_slug or "",
        "phase": phase,
        "run_id": run.id,
        "display_name": f"Run #{run.id}",
    }


def _session_to_agent(sess: CliSession) -> dict | None:
    """Convert a CliSession to an office agent dict."""
    if sess.status in ("closed", "error"):
        return None
    activity = (
        "coding" if sess.status == "active" else "idle" if sess.status == "idle" else "starting"
    )
    return {
        "id": f"session-{sess.session_id}",
        "agent_type": sess.agent_name or "generic",
        "room_id": sess.workspace_server_id or "platform",
        "desk": None,
        "status": sess.status,
        "activity": activity,
        "project": "",
        "phase": "session",
        "run_id": None,
        "display_name": sess.display_name or sess.agent_name or "Agent",
    }


def _local_session_to_agent(sess: LocalTerminalSession) -> dict | None:
    """Convert a LocalTerminalSession (platform chat) to an office agent dict."""
    if sess.status in ("closed", "error"):
        return None
    activity = (
        "coding" if sess.status == "active" else "idle" if sess.status == "idle" else "starting"
    )
    return {
        "id": f"local-{sess.session_id}",
        "agent_type": sess.agent_name or "generic",
        "room_id": "platform",
        "desk": None,
        "status": sess.status,
        "activity": activity,
        "project": "",
        "phase": "chat",
        "run_id": None,
        "display_name": sess.display_name or sess.agent_name or "Agent",
    }


async def _build_initial_state() -> dict:
    """Build the full office state snapshot."""
    async with async_session() as session:
        result = await session.execute(select(WorkspaceServer))
        servers = result.scalars().all()

        result = await session.execute(
            select(TaskRun).where(TaskRun.status.in_(["running", "pending"]))
        )
        runs = result.scalars().all()

        result = await session.execute(
            select(CliSession).where(
                CliSession.status.in_(["starting", "active", "idle", "detached"])
            )
        )
        cli_sessions = result.scalars().all()

        result = await session.execute(
            select(LocalTerminalSession).where(
                LocalTerminalSession.status.in_(["starting", "active", "idle"])
            )
        )
        local_sessions = result.scalars().all()

    rooms: list[dict] = [
        {
            "id": "platform",
            "name": "Platform",
            "status": "online",
            "capacity": None,
        }
    ]
    for s in servers:
        rooms.append(
            {
                "id": s.id,
                "name": s.name,
                "status": s.status or "unknown",
                "capacity": s.max_concurrent_tasks or 4,
            }
        )

    agents = []
    for r in runs:
        agent = _run_to_agent(r)
        if agent:
            agents.append(agent)
    for s in cli_sessions:
        agent = _session_to_agent(s)
        if agent:
            agents.append(agent)
    for s in local_sessions:
        agent = _local_session_to_agent(s)
        if agent:
            agents.append(agent)

    return {"type": "office_state", "rooms": rooms, "agents": agents}


def _translate_event(event: dict) -> dict | None:
    """Translate a Broadcaster global event into an office-specific event."""
    etype = event.get("type")
    run_id = event.get("run_id")

    if etype == "run_created":
        return {
            "type": "agent_spawned",
            "agent": {
                "id": f"run-{run_id}",
                "agent_type": event.get("agent_name", "generic"),
                "status": "starting",
                "activity": "starting",
                "project": event.get("project_slug", ""),
                "phase": "init",
                "run_id": run_id,
                "display_name": f"Run #{run_id}",
            },
            "room_id": "platform",
        }

    if etype == "phase_changed":
        phase = event.get("phase", "coding")
        activity = _PHASE_ACTIVITY.get(phase, "coding")
        server_id = event.get("workspace_server_id")
        if server_id:
            return {
                "type": "agent_moving",
                "agent_id": f"run-{run_id}",
                "from": "platform",
                "to": server_id,
                "activity": activity,
                "phase": phase,
            }
        return {
            "type": "activity_changed",
            "agent_id": f"run-{run_id}",
            "activity": activity,
            "phase": phase,
        }

    if etype == "status_changed":
        new_status = event.get("status")
        if new_status == "failed":
            return {
                "type": "agent_error",
                "agent_id": f"run-{run_id}",
                "error": event.get("error", "failed"),
            }
        if new_status in ("completed", "cancelled"):
            return {
                "type": "agent_finished",
                "agent_id": f"run-{run_id}",
            }

    return None


@router.websocket("/ws/office")
async def ws_office(websocket: WebSocket):
    """Stream office state and live agent events for the 8-bit office view."""
    await websocket.accept()
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)
    broadcaster.subscribe_office(queue)
    try:
        state = await _build_initial_state()
        await websocket.send_text(json.dumps(state, default=str))

        while True:
            event = await queue.get()
            # Direct office events (from office_event()) are already formatted
            if event.get("type") in (
                "agent_spawned",
                "agent_moving",
                "agent_seated",
                "activity_changed",
                "agent_error",
                "agent_finished",
                "agent_left",
                "room_status",
            ):
                await websocket.send_text(json.dumps(event, default=str))
                continue
            # TaskRun events need translation
            office_event = _translate_event(event)
            if office_event:
                await websocket.send_text(json.dumps(office_event, default=str))
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe_office(queue)
