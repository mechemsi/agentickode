# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""AgenticKode MCP server — exposes platform tools to AI agents.

Can run as:
  - stdio transport: for local agents in the same container
  - SSE transport: for remote agents connecting over HTTP

Usage:
    # stdio (for local agent subprocess)
    python -m backend.mcp.server

    # SSE is mounted on the FastAPI app at /mcp
"""

from __future__ import annotations

from fastmcp import FastMCP

from backend.mcp.tools.admin import (
    add_server,
    configure_agent,
    get_analytics,
    get_health,
    get_server_status,
    list_agents,
    list_servers,
    setup_server,
)
from backend.mcp.tools.agent_control import (
    approve_run,
    get_episodes,
    pause_agent,
    reject_run,
    resume_agent,
    send_message_to_agent,
)
from backend.mcp.tools.projects import (
    cancel_run,
    create_project,
    create_run,
    get_project,
    get_run,
    get_run_logs,
    list_projects,
    list_runs,
    update_project,
)

# Create the MCP server
mcp = FastMCP(
    "AgenticKode",
    instructions=(
        "You are connected to AgenticKode, an AI coding automation platform. "
        "Use these tools to manage projects, create task runs, control agents, "
        "and administer workspace servers. When asked to do coding tasks, "
        "create a run with create_run and monitor it with get_run."
    ),
)


# --- Tier 1: Project & Task Management ---
mcp.add_tool(list_projects)
mcp.add_tool(get_project)
mcp.add_tool(create_project)
mcp.add_tool(update_project)
mcp.add_tool(create_run)
mcp.add_tool(list_runs)
mcp.add_tool(get_run)
mcp.add_tool(get_run_logs)
mcp.add_tool(cancel_run)

# --- Tier 2: Agent Control ---
mcp.add_tool(get_episodes)
mcp.add_tool(send_message_to_agent)
mcp.add_tool(pause_agent)
mcp.add_tool(resume_agent)
mcp.add_tool(approve_run)
mcp.add_tool(reject_run)

# --- Tier 3: Administration ---
mcp.add_tool(list_servers)
mcp.add_tool(add_server)
mcp.add_tool(setup_server)
mcp.add_tool(get_server_status)
mcp.add_tool(list_agents)
mcp.add_tool(configure_agent)
mcp.add_tool(get_analytics)
mcp.add_tool(get_health)


def get_mcp_app():
    """Return the FastMCP server instance for mounting on FastAPI."""
    return mcp


if __name__ == "__main__":
    mcp.run()
