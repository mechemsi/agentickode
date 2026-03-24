# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent control endpoints — pause, resume, and send messages to running agents."""

from __future__ import annotations

import shlex

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import async_session
from backend.models import TaskRun
from backend.worker.phases._helpers import get_ssh_for_run

router = APIRouter(tags=["agent-control"])


class AgentMessage(BaseModel):
    message: str


@router.post("/runs/{run_id}/agent/message")
async def send_agent_message(run_id: int, body: AgentMessage):
    """Send a message to the running agent via tmux."""
    async with async_session() as session:
        run = await session.get(TaskRun, run_id)
        if not run or run.status != "running":
            raise HTTPException(404, "Run not found or not running")

        ssh = await get_ssh_for_run(run, session)
        tmux_name = f"autodev-{run_id}"

        # Send keys to tmux
        escaped = body.message.replace('"', '\\"')
        await ssh.run_command(
            f'tmux send-keys -t {tmux_name} "{escaped}" Enter 2>/dev/null || true',
            timeout=10,
        )

    return {"status": "sent"}


@router.post("/runs/{run_id}/agent/pause")
async def pause_agent(run_id: int):
    """Send Ctrl+C to pause the running agent."""
    async with async_session() as session:
        run = await session.get(TaskRun, run_id)
        if not run or run.status != "running":
            raise HTTPException(404, "Run not found or not running")

        ssh = await get_ssh_for_run(run, session)
        workspace = run.workspace_path or ""

        # Kill the claude process for this workspace
        ws = shlex.quote(workspace)
        await ssh.run_command(
            f"pkill -INT -f 'claude.*{ws}' 2>/dev/null || true",
            timeout=10,
        )

    return {"status": "paused"}


@router.post("/runs/{run_id}/agent/resume")
async def resume_agent(run_id: int, body: AgentMessage | None = None):
    """Resume the agent, optionally with new instructions."""
    async with async_session() as session:
        run = await session.get(TaskRun, run_id)
        if not run:
            raise HTTPException(404, "Run not found")

        # Re-queue the run for processing
        if run.status in ("failed", "completed"):
            raise HTTPException(400, "Cannot resume a finished run")

        if run.status != "running":
            run.status = "pending"
            await session.commit()

    return {"status": "resumed"}
