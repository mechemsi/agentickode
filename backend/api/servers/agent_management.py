# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent management endpoints for workspace servers."""

import json
import logging
import shlex

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from backend.database import get_db
from backend.models import DiscoveredAgent
from backend.models.agents import AgentSettings
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import (
    AgentInstallRequest,
    AgentInstallResult,
    AgentInstallStatus,
    AgentManagementStatus,
    UserAgentStatus,
)
from backend.services.workspace.agent_install_service import AgentInstallService
from backend.services.workspace.command_executor import executor_for_server
from backend.services.workspace.worker_user_service import WorkerUserService

logger = logging.getLogger("agentickode.agent_management")

router = APIRouter(tags=["agent-management"])


async def _load_agent_settings(db: AsyncSession) -> list[AgentSettings]:
    """Load all AgentSettings rows from DB."""
    result = await db.execute(select(AgentSettings))
    return list(result.scalars().all())


@router.get("/supported-agents")
async def list_supported_agents(db: AsyncSession = Depends(get_db)):
    """Return the list of all agents the platform can install."""
    settings = await _load_agent_settings(db)
    return [
        {
            "name": s.agent_name,
            "display_name": s.display_name,
            "description": s.description,
            "agent_type": s.agent_type or "cli_binary",
        }
        for s in settings
    ]


def _get_repo(db: AsyncSession = Depends(get_db)) -> WorkspaceServerRepository:
    return WorkspaceServerRepository(db)


@router.post(
    "/workspace-servers/{server_id}/agents/status",
    response_model=AgentManagementStatus,
)
async def get_agent_status(
    server_id: int,
    repo: WorkspaceServerRepository = Depends(_get_repo),
    db: AsyncSession = Depends(get_db),
):
    """Check install status of all supported agents (worker user only)."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    settings = await _load_agent_settings(db)
    ssh = executor_for_server(server)
    svc = AgentInstallService(ssh, agent_settings=settings)

    # Local platform server runs agents as the container user (no worker switch)
    is_local = getattr(server, "server_type", "remote") == "local"
    username = None if is_local else (server.worker_user or "coder")
    try:
        worker_agents = await svc.check_all_agents(as_user=username)
    except Exception:
        worker_agents = await svc.check_all_agents()

    agent_statuses = [
        AgentInstallStatus(
            agent_name=a.agent_name,
            display_name=a.display_name,
            description=a.description,
            agent_type=a.agent_type,
            installed=a.installed,
            version=a.version,
            path=a.path,
            authenticated=a.authenticated,
            auth_email=a.auth_email,
            auth_method=a.auth_method,
        )
        for a in worker_agents
    ]

    # Persist discovered worker agents to DB so list counts stay in sync
    try:
        db_agents = [
            DiscoveredAgent(
                agent_name=a.agent_name,
                agent_type=a.agent_type,
                path=a.path,
                version=a.version,
                available=a.installed,
            )
            for a in worker_agents
            if a.installed
        ]
        context = "admin" if is_local else "worker"
        await repo.replace_agents_for_context(server_id, context, db_agents)
    except Exception:
        logger.warning("Failed to persist agent status for server %s", server_id)

    by_user = [UserAgentStatus(user=username or "root", agents=agent_statuses)]
    return AgentManagementStatus(agents=agent_statuses, by_user=by_user)


@router.post(
    "/workspace-servers/{server_id}/agents/install",
    response_model=AgentInstallResult,
)
async def install_agent(
    server_id: int,
    body: AgentInstallRequest,
    repo: WorkspaceServerRepository = Depends(_get_repo),
    db: AsyncSession = Depends(get_db),
):
    """Install an agent directly on the worker user."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    settings = await _load_agent_settings(db)
    ssh = executor_for_server(server)
    svc = AgentInstallService(ssh, agent_settings=settings)

    is_local = getattr(server, "server_type", "remote") == "local"
    username = None if is_local else (server.worker_user or "coder")

    # Step 1: Ensure worker user exists (only for remote servers)
    if username:
        user_svc = WorkerUserService(ssh)
        user_info = await user_svc.setup(username)
        if not user_info.exists:
            return AgentInstallResult(
                success=False,
                agent_name=body.agent_name,
                error=f"Failed to create worker user '{username}': {user_info.error}",
            )

    # Step 2: Install agent
    result = await svc.install_agent(body.agent_name, as_user=username)
    if not result.success:
        return AgentInstallResult(
            success=False,
            agent_name=result.agent_name,
            error=result.error,
            output=result.output,
        )

    target = f"worker user '{username}'" if username else "platform"
    return AgentInstallResult(
        success=True,
        agent_name=body.agent_name,
        message=f"{body.agent_name} installed for {target}",
        output=result.output,
    )


@router.post("/workspace-servers/{server_id}/agents/install-stream")
async def install_agent_stream(
    server_id: int,
    body: AgentInstallRequest,
    repo: WorkspaceServerRepository = Depends(_get_repo),
    db: AsyncSession = Depends(get_db),
):
    """Stream agent installation progress via SSE."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    settings = await _load_agent_settings(db)
    ssh = executor_for_server(server)
    svc = AgentInstallService(ssh, agent_settings=settings)

    is_local = getattr(server, "server_type", "remote") == "local"
    username = None if is_local else (server.worker_user or "coder")

    # Ensure worker user exists (only for remote servers)
    user_info = None
    if username:
        user_svc = WorkerUserService(ssh)
        user_info = await user_svc.setup(username)

    async def event_generator():
        if user_info is not None and not user_info.exists:
            msg = f"Failed to create worker user '{username}': {user_info.error}"
            yield f"data: {json.dumps({'type': 'error', 'line': msg})}\n\n"
            return

        async for line in svc.install_agent_stream(body.agent_name, as_user=username):
            yield f"data: {json.dumps({'type': 'output', 'line': line})}\n\n"

        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/workspace-servers/{server_id}/agents/install-worker",
    response_model=AgentInstallResult,
    deprecated=True,
)
async def install_agent_for_worker(
    server_id: int,
    body: AgentInstallRequest,
    repo: WorkspaceServerRepository = Depends(_get_repo),
    db: AsyncSession = Depends(get_db),
):
    """Deprecated: use /install which now does combined install+copy."""
    return await install_agent(server_id, body, repo, db)


@router.post("/workspace-servers/{server_id}/agents/{agent_name}/auth-login")
async def start_agent_auth_login(
    server_id: int,
    agent_name: str,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Start an interactive auth login flow for an agent in a tmux session."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    login_commands = {
        "claude": "claude",
    }
    login_cmd = login_commands.get(agent_name)
    if not login_cmd:
        raise HTTPException(400, f"Agent '{agent_name}' does not support interactive auth login")

    username = server.worker_user or "coder"
    ssh = executor_for_server(server)

    # Ensure tmux is installed
    _out, _err, rc_check = await ssh.run_command("command -v tmux")
    if rc_check != 0:
        await ssh.run_command(
            "apt-get update -qq && apt-get install -y -qq tmux >/dev/null 2>&1 "
            "|| yum install -y -q tmux 2>/dev/null "
            "|| apk add --no-cache tmux 2>/dev/null",
            timeout=60,
        )

    tmux_name = f"auth-{agent_name}-{server_id}"

    # Kill any existing auth session
    kill_cmd = f"tmux kill-session -t {shlex.quote(tmux_name)} 2>/dev/null || true"
    await ssh.run_command(kill_cmd, timeout=5)

    # Create tmux session as worker user (shell stays alive if command exits)
    def _as_user(cmd: str) -> str:
        return f"runuser -l {shlex.quote(username)} -c {shlex.quote(cmd)}"

    create_cmd = f"tmux new-session -d -s {shlex.quote(tmux_name)} -x 200 -y 50"
    await ssh.run_command(_as_user(create_cmd), timeout=10)

    # Enable mouse scrolling and increase scrollback
    await ssh.run_command(
        _as_user(
            f"tmux set-option -t {shlex.quote(tmux_name)} mouse on && "
            f"tmux set-option -t {shlex.quote(tmux_name)} history-limit 10000"
        ),
        timeout=5,
    )

    # Send the login command into the tmux session
    await ssh.run_command(
        _as_user(f"tmux send-keys -t {shlex.quote(tmux_name)} {shlex.quote(login_cmd)} Enter"),
        timeout=5,
    )

    return {
        "tmux_session": tmux_name,
        "server_id": server_id,
        "agent_name": agent_name,
    }


@router.delete("/workspace-servers/{server_id}/agents/{agent_name}/auth-login")
async def stop_agent_auth_login(
    server_id: int,
    agent_name: str,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Kill the auth login tmux session for an agent."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    username = server.worker_user or "coder"
    ssh = executor_for_server(server)
    tmux_name = f"auth-{agent_name}-{server_id}"

    kill_cmd = f"tmux kill-session -t {shlex.quote(tmux_name)} 2>/dev/null || true"
    wrapped = f"runuser -l {shlex.quote(username)} -c {shlex.quote(kill_cmd)}"
    await ssh.run_command(wrapped, timeout=5)

    return {"success": True}
