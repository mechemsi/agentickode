# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""MCP tools — Tier 3: Platform administration."""

from __future__ import annotations

from fastmcp import Context

from backend.mcp.tools.projects import _api


async def list_servers(ctx: Context) -> list:
    """List all workspace servers with their status and installed agents."""
    return await _api(ctx, "get", "/workspace-servers")


async def add_server(
    ctx: Context,
    hostname: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    ssh_key_id: int | None = None,
) -> dict:
    """Add a new workspace server.

    Args:
        hostname: Server hostname or IP address
        ssh_user: SSH user (default: root)
        ssh_port: SSH port (default: 22)
        ssh_key_id: ID of SSH key pair to use for connection
    """
    body: dict = {"hostname": hostname, "ssh_user": ssh_user, "ssh_port": ssh_port}
    if ssh_key_id is not None:
        body["ssh_key_id"] = ssh_key_id
    return await _api(ctx, "post", "/workspace-servers", json=body)


async def setup_server(ctx: Context, server_id: int) -> dict:
    """Run setup on a workspace server.

    Installs AI agents, creates worker user, configures git access.
    """
    return await _api(ctx, "post", f"/workspace-servers/{server_id}/setup")


async def get_server_status(ctx: Context, server_id: int) -> dict:
    """Get detailed server status including installed agents and active runs."""
    return await _api(ctx, "get", f"/workspace-servers/{server_id}")


async def list_agents(ctx: Context) -> list:
    """List all configured AI agents with their settings and availability."""
    return await _api(ctx, "get", "/agents")


async def configure_agent(
    ctx: Context,
    agent_name: str,
    timeout: int | None = None,
    enabled: bool | None = None,
) -> dict:
    """Update AI agent settings.

    Args:
        agent_name: Agent to configure (claude, codex, gemini, etc.)
        timeout: Default timeout in seconds
        enabled: Whether the agent is enabled
    """
    body: dict = {}
    if timeout is not None:
        body["default_timeout"] = timeout
    if enabled is not None:
        body["enabled"] = enabled
    return await _api(ctx, "put", f"/agents/{agent_name}", json=body)


async def get_analytics(ctx: Context, period: str = "7d") -> dict:
    """Get platform analytics — run counts, costs, success rates.

    Args:
        period: Time period (7d, 30d, 90d)
    """
    return await _api(ctx, "get", "/analytics/summary", params={"period": period})


async def get_health(ctx: Context) -> dict:
    """Get platform health status — database, worker, queue, services."""
    return await _api(ctx, "get", "/health")
