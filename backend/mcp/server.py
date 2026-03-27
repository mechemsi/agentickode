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
    create_run_and_wait,
    get_episodes,
    get_run_diff,
    get_run_plan,
    pause_agent,
    query_run_agent,
    reject_run,
    resume_agent,
    send_message_to_agent,
)
from backend.mcp.tools.automation import (
    create_automation_rule,
    list_automation_rules,
    update_automation_rule,
)
from backend.mcp.tools.memory import (
    query_org_memory,
    store_knowledge,
    sync_obsidian_vault,
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
from backend.mcp.tools.scheduling import (
    create_scheduled_task,
    list_scheduled_tasks,
    trigger_scheduled_task,
    update_scheduled_task,
)
from backend.mcp.tools.sessions import (
    capture_session_output,
    close_workspace_session,
    create_workspace_session,
    get_workspace_session,
    list_workspace_sessions,
    send_to_session,
)
from backend.mcp.tools.workspace import (
    list_workspace_directory,
    read_workspace_file,
    run_workspace_command,
)

# Create the MCP server
mcp = FastMCP(
    "AgenticKode",
    instructions=(
        "You are the AI team manager for AgenticKode, a coding automation platform.\n\n"
        "TOOLS BY TIER:\n"
        "1. Projects: list_projects, get_project, create_project, create_run, list_runs, get_run\n"
        "2. Agent Control: query_run_agent, get_run_diff, approve_run, create_run_and_wait\n"
        "3. Admin: list_servers, list_agents, get_health, get_analytics\n"
        "4. Sessions: create_workspace_session, send_to_session, capture_session_output, close_workspace_session\n"
        "5. Workspace: run_workspace_command, read_workspace_file, list_workspace_directory\n\n"
        "WORKFLOW FOR CODING TASKS:\n"
        "1. Use create_workspace_session to start an agent on a workspace server\n"
        "2. Use send_to_session to give it a task\n"
        "3. Wait 20-60 seconds, then use capture_session_output to check progress\n"
        "4. Repeat capture until the agent finishes, then report results to the user\n"
        "5. If the agent asks a question, relay it to the user and send the answer back\n\n"
        "For pipeline tasks (with PR creation), use create_run or create_run_and_wait instead.\n"
        "Use run_workspace_command for quick operations (run tests, check files, git status).\n"
        "Always report what workspace agents say back to the user."
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
mcp.add_tool(query_run_agent)
mcp.add_tool(get_run_diff)
mcp.add_tool(get_run_plan)
mcp.add_tool(create_run_and_wait)

# --- Tier 3: Administration ---
mcp.add_tool(list_servers)
mcp.add_tool(add_server)
mcp.add_tool(setup_server)
mcp.add_tool(get_server_status)
mcp.add_tool(list_agents)
mcp.add_tool(configure_agent)
mcp.add_tool(get_analytics)
mcp.add_tool(get_health)

# --- Tier 4: Workspace Sessions ---
mcp.add_tool(create_workspace_session)
mcp.add_tool(send_to_session)
mcp.add_tool(capture_session_output)
mcp.add_tool(get_workspace_session)
mcp.add_tool(list_workspace_sessions)
mcp.add_tool(close_workspace_session)

# --- Tier 5: Remote Workspace Commands ---
mcp.add_tool(run_workspace_command)
mcp.add_tool(read_workspace_file)
mcp.add_tool(list_workspace_directory)

# --- Tier 6: Scheduling ---
mcp.add_tool(list_scheduled_tasks)
mcp.add_tool(create_scheduled_task)
mcp.add_tool(update_scheduled_task)
mcp.add_tool(trigger_scheduled_task)

# --- Tier 7: Automation Rules ---
mcp.add_tool(list_automation_rules)
mcp.add_tool(create_automation_rule)
mcp.add_tool(update_automation_rule)

# --- Tier 8: Memory & Knowledge ---
mcp.add_tool(query_org_memory)
mcp.add_tool(store_knowledge)
mcp.add_tool(sync_obsidian_vault)


def get_mcp_app():
    """Return the FastMCP server instance for mounting on FastAPI."""
    return mcp


if __name__ == "__main__":
    mcp.run()
