# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""WebSocket endpoints for live log streaming, global events, and SSH terminals."""

import asyncio
import json
import logging

import asyncssh
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.database import async_session
from backend.models import ProjectConfig, TaskRun, WorkspaceServer
from backend.services.workspace.ssh_service import SSHService
from backend.worker.broadcaster import broadcaster

logger = logging.getLogger("agentickode.ws")
router = APIRouter()


@router.websocket("/ws/runs/{run_id}/logs")
async def ws_run_logs(websocket: WebSocket, run_id: int):
    """Stream logs for a specific run in real-time."""
    await websocket.accept()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    broadcaster.subscribe_run(run_id, queue)
    try:
        while True:
            msg = await queue.get()
            await websocket.send_text(json.dumps(msg))
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe_run(run_id, queue)


@router.websocket("/ws/events")
async def ws_global_events(websocket: WebSocket):
    """Stream global status-change events (run created, phase changed, completed, etc.)."""
    await websocket.accept()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    broadcaster.subscribe_global(queue)
    try:
        while True:
            msg = await queue.get()
            await websocket.send_text(json.dumps(msg))
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe_global(queue)


@router.websocket("/ws/servers/{server_id}/terminal")
async def ws_terminal(websocket: WebSocket, server_id: int):
    """Bridge a browser xterm.js session to an SSH PTY on the workspace server."""
    await websocket.accept()

    async with async_session() as session:
        result = await session.execute(
            select(WorkspaceServer).where(WorkspaceServer.id == server_id)
        )
        server = result.scalar_one_or_none()

    if not server:
        await websocket.send_text(json.dumps({"type": "output", "data": "Server not found.\r\n"}))
        await websocket.close()
        return

    ssh = SSHService.for_server(server)
    try:
        conn = await ssh._connect()
    except Exception as exc:
        await websocket.send_text(
            json.dumps({"type": "output", "data": f"SSH connection failed: {exc}\r\n"})
        )
        await websocket.close()
        return

    try:
        process = await conn.create_process(
            "bash",
            term_type="xterm-256color",
            term_size=(120, 40),
        )
    except Exception as exc:
        await websocket.send_text(
            json.dumps({"type": "output", "data": f"Failed to start shell: {exc}\r\n"})
        )
        conn.close()
        await websocket.close()
        return

    async def ssh_to_ws():
        try:
            while True:
                data = await process.stdout.read(4096)
                if not data:
                    break
                await websocket.send_text(json.dumps({"type": "output", "data": data}))
        except (asyncssh.BreakReceived, asyncssh.SignalReceived, asyncssh.TerminalSizeChanged):
            pass
        except Exception:
            pass

    async def ws_to_ssh():
        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                if msg.get("type") == "input":
                    process.stdin.write(msg["data"])
                elif msg.get("type") == "resize":
                    process.change_terminal_size(msg.get("cols", 120), msg.get("rows", 40))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    read_task = asyncio.create_task(ssh_to_ws())
    write_task = asyncio.create_task(ws_to_ssh())
    try:
        await asyncio.gather(read_task, write_task, return_exceptions=True)
    finally:
        process.close()
        conn.close()


@router.websocket("/ws/runs/{run_id}/terminal")
async def ws_run_terminal(websocket: WebSocket, run_id: int):
    """Bridge xterm.js to SSH PTY in the run's workspace, optionally resuming a Claude session."""
    await websocket.accept()

    # Look up run and resolve workspace server
    async with async_session() as session:
        run = await session.get(TaskRun, run_id)
        if not run:
            await websocket.send_text(json.dumps({"type": "output", "data": "Run not found.\r\n"}))
            await websocket.close()
            return

        meta = run.task_source_meta or {}
        server_id = meta.get("workspace_server_id")
        if not server_id:
            project = await session.get(ProjectConfig, run.project_id)
            if project:
                server_id = project.workspace_server_id
        if not server_id:
            await websocket.send_text(
                json.dumps({"type": "output", "data": "No workspace server configured.\r\n"})
            )
            await websocket.close()
            return

        result = await session.execute(
            select(WorkspaceServer).where(WorkspaceServer.id == server_id)
        )
        server = result.scalar_one_or_none()

    if not server:
        await websocket.send_text(json.dumps({"type": "output", "data": "Server not found.\r\n"}))
        await websocket.close()
        return

    ssh = SSHService.for_server(server)
    try:
        conn = await ssh._connect()
    except Exception as exc:
        await websocket.send_text(
            json.dumps({"type": "output", "data": f"SSH connection failed: {exc}\r\n"})
        )
        await websocket.close()
        return

    # Build startup command
    workspace_root = server.workspace_root or "/home/coder"
    workspace_path = run.workspace_path or ""
    if workspace_path.startswith("/"):
        full_path = workspace_path
    else:
        full_path = f"{workspace_root}/{workspace_path}".rstrip("/")

    coding_results = run.coding_results or {}
    session_id = coding_results.get("session_id")

    if session_id:
        shell_cmd = f"cd {full_path} && claude --resume {session_id}"
    else:
        shell_cmd = f"cd {full_path} && bash"

    worker_user = server.worker_user
    if worker_user:
        import shlex

        shell_cmd = f"runuser -l {worker_user} -c {shlex.quote(shell_cmd)}"

    try:
        process = await conn.create_process(
            shell_cmd,
            term_type="xterm-256color",
            term_size=(120, 40),
        )
    except Exception as exc:
        await websocket.send_text(
            json.dumps({"type": "output", "data": f"Failed to start shell: {exc}\r\n"})
        )
        conn.close()
        await websocket.close()
        return

    async def ssh_to_ws():
        try:
            while True:
                data = await process.stdout.read(4096)
                if not data:
                    break
                await websocket.send_text(json.dumps({"type": "output", "data": data}))
        except (asyncssh.BreakReceived, asyncssh.SignalReceived, asyncssh.TerminalSizeChanged):
            pass
        except Exception:
            pass

    async def ws_to_ssh():
        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                if msg.get("type") == "input":
                    process.stdin.write(msg["data"])
                elif msg.get("type") == "resize":
                    process.change_terminal_size(msg.get("cols", 120), msg.get("rows", 40))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    read_task = asyncio.create_task(ssh_to_ws())
    write_task = asyncio.create_task(ws_to_ssh())
    try:
        await asyncio.gather(read_task, write_task, return_exceptions=True)
    finally:
        process.close()
        conn.close()
