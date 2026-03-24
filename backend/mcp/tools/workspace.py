# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""MCP tools — Remote workspace command execution.

Execute commands, read files, and list directories on workspace servers
directly via SSH. The platform agent can use these to inspect workspaces,
run tests, check logs, and more — without creating a full agent session.
"""

from __future__ import annotations

from fastmcp import Context

from backend.mcp.tools.projects import _api


async def run_workspace_command(
    ctx: Context,
    server_id: int,
    command: str,
    timeout: int = 30,
    user: str | None = None,
) -> dict:
    """Execute a shell command on a workspace server via SSH.

    Returns stdout, stderr, and exit code. Use this for quick operations:
    checking files, running tests, inspecting logs, git operations, etc.

    Args:
        server_id: Workspace server to run on
        command: Shell command to execute
        timeout: Max seconds to wait (default 30)
        user: Optional user to run as (e.g., 'coder' for non-root)
    """
    body: dict = {"command": command, "timeout": timeout}
    if user:
        body["user"] = user
    return await _api(ctx, "post", f"/workspace-servers/{server_id}/exec", json=body)


async def read_workspace_file(ctx: Context, server_id: int, file_path: str) -> dict:
    """Read a file from a workspace server.

    Args:
        server_id: Workspace server
        file_path: Absolute path to the file on the remote server
    """
    return await _api(
        ctx, "get", f"/workspace-servers/{server_id}/read-file", params={"path": file_path}
    )


async def list_workspace_directory(ctx: Context, server_id: int, path: str = "/") -> dict:
    """List files in a directory on a workspace server.

    Args:
        server_id: Workspace server
        path: Directory path to list (default: /)
    """
    return await _api(ctx, "get", f"/workspace-servers/{server_id}/ls", params={"path": path})
