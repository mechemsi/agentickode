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
