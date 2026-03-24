# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""WebSocket endpoints for live log streaming, global events, SSH and local terminals."""

import asyncio
import json
import logging
import os
import shlex
from datetime import UTC, datetime

import asyncssh
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.database import async_session
from backend.models import ProjectWorkspaceServer, TaskRun, WorkspaceServer
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
async def ws_terminal(websocket: WebSocket, server_id: int, user: str | None = None):
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

    # Determine shell command based on user selection
    shell_cmd = "bash"
    if user == "worker" and server.worker_user:
        shell_cmd = f"runuser -l {server.worker_user} -c {shlex.quote('bash')}"

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
        server_id = meta.get("workspace_server_id") or run.workspace_server_id
        if not server_id:
            # Fall back to highest-priority workspace server for the project
            pws_result = await session.execute(
                select(ProjectWorkspaceServer.workspace_server_id)
                .where(ProjectWorkspaceServer.project_id == run.project_id)
                .order_by(ProjectWorkspaceServer.priority)
                .limit(1)
            )
            server_id = pws_result.scalar_one_or_none()
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
    run_session_id = coding_results.get("session_id")

    if run_session_id:
        shell_cmd = f"cd {full_path} && claude --resume {run_session_id}"
    else:
        shell_cmd = f"cd {full_path} && bash"

    worker_user = server.worker_user
    if worker_user:
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


@router.websocket("/ws/sessions/{session_id}/terminal")
async def ws_session_terminal(websocket: WebSocket, session_id: str):
    """Attach a browser xterm.js session to an existing tmux-managed CLI session."""
    await websocket.accept()

    # Load session from DB
    async with async_session() as db:
        from backend.models.sessions import CliSession

        result = await db.execute(select(CliSession).where(CliSession.session_id == session_id))
        cli_session = result.scalar_one_or_none()

    if not cli_session:
        await websocket.send_text(json.dumps({"type": "output", "data": "Session not found.\r\n"}))
        await websocket.close()
        return

    if cli_session.status == "closed":
        await websocket.send_text(json.dumps({"type": "output", "data": "Session is closed.\r\n"}))
        await websocket.close()
        return

    # Load workspace server
    async with async_session() as db:
        result = await db.execute(
            select(WorkspaceServer).where(WorkspaceServer.id == cli_session.workspace_server_id)
        )
        server = result.scalar_one_or_none()

    if not server:
        await websocket.send_text(json.dumps({"type": "output", "data": "Server not found.\r\n"}))
        await websocket.close()
        return

    # Connect via SSH
    ssh = SSHService.for_server(server)
    try:
        conn = await ssh._connect()
    except Exception as exc:
        await websocket.send_text(
            json.dumps({"type": "output", "data": f"SSH connection failed: {exc}\r\n"})
        )
        await websocket.close()
        return

    # Attach to tmux session
    tmux_cmd = f"tmux attach-session -t {shlex.quote(cli_session.tmux_session)}"

    try:
        process = await conn.create_process(
            tmux_cmd,
            term_type="xterm-256color",
            term_size=(120, 40),
        )
    except Exception as exc:
        await websocket.send_text(
            json.dumps({"type": "output", "data": f"Failed to attach to session: {exc}\r\n"})
        )
        conn.close()
        await websocket.close()
        return

    # Update session status to active
    async with async_session() as db:
        result = await db.execute(select(CliSession).where(CliSession.session_id == session_id))
        s = result.scalar_one_or_none()
        if s:
            s.status = "active"
            s.last_activity_at = datetime.now(UTC)
            await db.commit()

    # Bridge SSH PTY <-> WebSocket (same pattern as existing ws_terminal)
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
        # Mark session as detached on disconnect
        async with async_session() as db:
            result = await db.execute(select(CliSession).where(CliSession.session_id == session_id))
            s = result.scalar_one_or_none()
            if s and s.status == "active":
                s.status = "detached"
                s.last_activity_at = datetime.now(UTC)
                await db.commit()


@router.websocket("/ws/local-terminal/{agent_name}")
async def ws_local_terminal(websocket: WebSocket, agent_name: str):
    """Local terminal — runs an agent interactively inside the platform container.

    Creates a local tmux session, launches the agent, and bridges the PTY
    to the browser via xterm.js. No SSH needed — runs in-process.
    """
    import fcntl
    import pty
    import struct
    import termios

    await websocket.accept()

    tmux_name = f"chat-{agent_name}-{os.getpid()}"
    agent_path = shlex.quote(agent_name)
    env = {
        **os.environ,
        "TERM": "xterm-256color",
        "PATH": f"/root/.local/bin:/root/.local/share/claude/bin:{os.environ.get('PATH', '')}",
    }

    # Create tmux session with the agent
    tmux_create = f"tmux new-session -d -s {tmux_name} -x 120 -y 40 {agent_path}"
    proc = await asyncio.create_subprocess_shell(
        tmux_create,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()

    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        await websocket.send_text(
            json.dumps(
                {
                    "type": "output",
                    "data": f"Failed to start {agent_name}: {stderr}\r\n",
                }
            )
        )
        await websocket.close()
        return

    # Attach to tmux via a local PTY
    master_fd, slave_fd = pty.openpty()

    attach_cmd = f"tmux attach-session -t {tmux_name}"
    attach_proc = await asyncio.create_subprocess_shell(
        attach_cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        preexec_fn=os.setsid,
    )
    os.close(slave_fd)

    loop = asyncio.get_event_loop()

    async def pty_to_ws():
        """Read from PTY master and send to WebSocket."""
        try:
            while True:
                data = await loop.run_in_executor(None, os.read, master_fd, 4096)
                if not data:
                    break
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "output",
                            "data": data.decode("utf-8", errors="replace"),
                        }
                    )
                )
        except OSError:
            pass
        except Exception:
            pass

    async def ws_to_pty():
        """Read from WebSocket and write to PTY master."""
        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                if msg.get("type") == "input":
                    os.write(master_fd, msg["data"].encode("utf-8"))
                elif msg.get("type") == "resize":
                    cols = msg.get("cols", 120)
                    rows = msg.get("rows", 40)
                    winsize = struct.pack("HHHH", rows, cols, 0, 0)
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                    # Also resize tmux
                    await asyncio.create_subprocess_shell(
                        f"tmux resize-window -t {tmux_name} -x {cols} -y {rows}",
                        env=env,
                    )
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    read_task = asyncio.create_task(pty_to_ws())
    write_task = asyncio.create_task(ws_to_pty())
    try:
        await asyncio.gather(read_task, write_task, return_exceptions=True)
    finally:
        os.close(master_fd)
        attach_proc.kill()
        # Clean up tmux session
        await asyncio.create_subprocess_shell(f"tmux kill-session -t {tmux_name} 2>/dev/null")
