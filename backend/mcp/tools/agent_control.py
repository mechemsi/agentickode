# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""MCP tools — Tier 2: Live agent interaction and control."""

from __future__ import annotations

from fastmcp import Context

from backend.mcp.tools.projects import _api


async def get_episodes(ctx: Context, run_id: int) -> list:
    """List episodes for an episodic autonomous execution run.

    Shows episode number, status, turn count, tokens used, context usage,
    and git checkpoint SHA for each episode.
    """
    return await _api(ctx, "get", f"/runs/{run_id}/episodes")


async def send_message_to_agent(ctx: Context, run_id: int, message: str) -> dict:
    """Send a message to a running autonomous agent to redirect its focus.

    The message is delivered to the agent's input. Use this to give
    additional instructions or change priorities mid-execution.
    """
    return await _api(ctx, "post", f"/runs/{run_id}/agent/message", json={"message": message})


async def pause_agent(ctx: Context, run_id: int) -> dict:
    """Pause a running autonomous agent by sending an interrupt signal."""
    return await _api(ctx, "post", f"/runs/{run_id}/agent/pause")


async def resume_agent(ctx: Context, run_id: int) -> dict:
    """Resume a paused autonomous agent."""
    return await _api(ctx, "post", f"/runs/{run_id}/agent/resume")


async def approve_run(ctx: Context, run_id: int) -> dict:
    """Approve a run that is waiting for human approval.

    This advances the run to the finalization phase (merge PR, notify, etc.).
    """
    return await _api(ctx, "post", f"/runs/{run_id}/approve")


async def reject_run(ctx: Context, run_id: int, reason: str | None = None) -> dict:
    """Reject a run that is waiting for approval.

    Args:
        run_id: The run to reject
        reason: Optional reason for rejection
    """
    body = {"reason": reason} if reason else {}
    return await _api(ctx, "post", f"/runs/{run_id}/reject", json=body)


async def query_run_agent(ctx: Context, run_id: int, question: str, timeout: int = 120) -> dict:
    """Send a question to a run's agent and get a response.

    Uses the agent's session to continue the conversation, so the agent
    has full context of what it did during the run. Use this to ask the
    workspace agent about its work, what files it changed, or why it
    made certain decisions.

    Args:
        run_id: The task run whose agent to query
        question: The question to ask the agent
        timeout: Max seconds to wait for response (default 120)
    """
    return await _api(
        ctx,
        "post",
        f"/runs/{run_id}/agent/query",
        json={"question": question, "timeout": timeout},
    )


async def get_run_diff(ctx: Context, run_id: int) -> dict:
    """Get the git diff of changes made by the agent in a task run.

    Returns a summary (file names and line counts) and the actual diff content.
    Use this to review what the agent changed before approving.
    """
    return await _api(ctx, "get", f"/runs/{run_id}/agent/diff")


async def get_run_plan(ctx: Context, run_id: int) -> dict:
    """Get the agent's implementation plan for a task run.

    Returns the plan from .autodev/plan.json if the agent created one.
    """
    return await _api(ctx, "get", f"/runs/{run_id}/agent/plan")


async def create_run_and_wait(
    ctx: Context,
    project_id: str,
    title: str,
    description: str = "",
    execution_mode: str | None = None,
    timeout: int = 3600,
) -> dict:
    """Create a task run and wait for it to complete.

    This is a blocking call — it creates the run, then polls until
    the run completes, fails, or times out. Returns the final status
    including PR URL if created.

    Use this for orchestrating multi-step workflows where you need
    one task to finish before starting the next.

    Args:
        project_id: Project to run the task on
        title: Task title
        description: Detailed task description
        execution_mode: Override mode (structured/autonomous/hybrid)
        timeout: Max seconds to wait (default 3600 = 1 hour)
    """
    body: dict = {
        "project_id": project_id,
        "title": title,
        "description": description,
        "timeout": timeout,
    }
    if execution_mode:
        body["execution_mode"] = execution_mode
    return await _api(ctx, "post", "/runs/create-and-wait", json=body)
