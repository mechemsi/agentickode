# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""MCP tools — Workspace session management.

Create, manage, and communicate with persistent AI agent sessions
running on workspace servers. These sessions are independent of task runs.
"""

from __future__ import annotations

from fastmcp import Context

from backend.mcp.tools.projects import _api


async def create_workspace_session(
    ctx: Context,
    server_id: int,
    agent_name: str = "claude",
    project_id: str | None = None,
    workspace_path: str | None = None,
    user_context: str = "coder",
    display_name: str | None = None,
) -> dict:
    """Create a persistent AI agent session on a workspace server.

    Launches the specified agent in a tmux session on the remote server.
    The session persists until explicitly closed. Use send_to_session()
    to interact with it.

    Args:
        server_id: Workspace server to create the session on
        agent_name: Agent to launch (claude, codex, gemini, aider, opencode)
        project_id: Optional project ID for context
        workspace_path: Directory to start the session in
        user_context: User to run as (default: coder)
        display_name: Human-readable session name
    """
    body: dict = {
        "workspace_server_id": server_id,
        "agent_name": agent_name,
        "user_context": user_context,
    }
    if project_id:
        body["project_id"] = project_id
    if workspace_path:
        body["workspace_path"] = workspace_path
    if display_name:
        body["display_name"] = display_name
    return await _api(ctx, "post", "/sessions", json=body)


async def send_to_session(ctx: Context, session_id: int, message: str) -> dict:
    """Send a command or prompt to a running workspace session.

    The message is typed into the agent's tmux session. After a brief
    delay, the current pane output is captured and returned.

    Args:
        session_id: Numeric session ID (not the UUID)
        message: Text to send to the agent
    """
    return await _api(ctx, "post", f"/sessions/{session_id}/send", json={"message": message})


async def capture_session_output(ctx: Context, session_id: int, lines: int = 50) -> dict:
    """Read the current output from a workspace session.

    Captures the tmux pane content (last N lines). Use this to check
    what the agent is currently doing or has produced.

    Args:
        session_id: Numeric session ID
        lines: Number of lines to capture (default 50)
    """
    return await _api(ctx, "get", f"/sessions/{session_id}/capture", params={"lines": lines})


async def get_workspace_session(ctx: Context, session_id: int) -> dict:
    """Get details of a workspace session including status and agent info."""
    return await _api(ctx, "get", f"/sessions/{session_id}")


async def list_workspace_sessions(
    ctx: Context,
    server_id: int | None = None,
    project_id: str | None = None,
    status: str | None = None,
) -> list:
    """List workspace sessions across servers.

    Args:
        server_id: Filter by workspace server
        project_id: Filter by project
        status: Filter by status (active/idle/closed)
    """
    params: dict = {}
    if server_id:
        params["server_id"] = server_id
    if project_id:
        params["project_id"] = project_id
    if status:
        params["status"] = status
    return await _api(ctx, "get", "/sessions", params=params)


async def close_workspace_session(ctx: Context, session_id: int) -> dict:
    """Close a workspace session and kill the agent process.

    The tmux session is destroyed and the session is marked as closed in the database.
    """
    return await _api(ctx, "delete", f"/sessions/{session_id}")
